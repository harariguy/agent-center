"""Remote MCP over streamable HTTP — a JSON-RPC endpoint at POST /mcp.

Hand-rolled rather than pulled from the MCP SDK, for one decisive reason: here
the bearer token *is* the agent identity, so every tool call must resolve the
calling agent from the raw HTTP request. That is a one-line FastAPI dependency
(`require_agent`, already the ingest path's auth) versus reaching for the
request from inside an SDK tool context and hand-wiring a mounted sub-app's
lifespan into this app's. This server is stateless and tools-only, which is the
case where streamable HTTP reduces to JSON-RPC over POST and little else.

Statelessness is the design, not a shortcut: no session id is issued, so any
number of clients (and any number of uvicorn workers) can share one endpoint,
and a client reconnecting has nothing to resume. Consequently there is no
server-initiated stream — GET returns 405 — and no session to terminate.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import __version__
from ..auth import get_db, require_agent
from ..db.models import Agent
from ..docs import GUIDE
from . import tools

log = logging.getLogger("agent_center.mcp")

router = APIRouter(tags=["mcp"], include_in_schema=False)

# Newest first. We accept any of these and echo back what the client asked for
# when we know it, which is what the spec's negotiation amounts to for a server
# whose surface has not changed across these revisions.
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL = SUPPORTED_PROTOCOLS[0]

SERVER_INFO = {
    "name": "agent-center",
    "title": "Agent Center",
    "version": __version__,
}

# JSON-RPC 2.0 error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _handle(message: dict, ctx: tools.ToolContext) -> dict | None:
    """One JSON-RPC message in, one response out — or None for a notification."""
    if not isinstance(message, dict):
        return _error(None, INVALID_REQUEST, "Each message must be a JSON object.")

    method = message.get("method")
    # No "id" means a JSON-RPC notification: never answer it, not even to complain.
    is_notification = "id" not in message
    msg_id = message.get("id")

    if not isinstance(method, str):
        return None if is_notification else _error(msg_id, INVALID_REQUEST, "Missing 'method'.")

    params = message.get("params") or {}
    if not isinstance(params, dict):
        return None if is_notification else _error(msg_id, INVALID_PARAMS, "'params' must be an object.")

    if is_notification:
        return None

    if method == "initialize":
        asked = params.get("protocolVersion")
        return _result(msg_id, {
            "protocolVersion": asked if asked in SUPPORTED_PROTOCOLS else LATEST_PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            # The usage contract travels with the connection, so every client
            # gets the field discipline without anyone copying a skill file.
            "instructions": GUIDE,
        })

    if method == "ping":
        return _result(msg_id, {})

    if method == "tools/list":
        return _result(msg_id, {"tools": tools.descriptors()})

    if method == "tools/call":
        name = params.get("name")
        if name not in tools.BY_NAME:
            return _error(msg_id, INVALID_PARAMS,
                          f"Unknown tool '{name}'. Available: {', '.join(tools.BY_NAME)}.")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(msg_id, INVALID_PARAMS, "'arguments' must be an object.")
        try:
            outcome = tools.call(ctx, name, arguments)
        except Exception:  # a tool bug must not take the connection down
            log.exception("mcp tool %s failed", name)
            ctx.db.rollback()
            outcome = tools.ToolResult(
                f"Agent Center failed to handle {name}. This is a server-side fault, not a "
                f"problem with your arguments; do not retry in a loop.",
                is_error=True,
            )
        payload: dict = {
            "content": [{"type": "text", "text": outcome.text}],
            "isError": outcome.is_error,
        }
        if outcome.structured is not None:
            payload["structuredContent"] = outcome.structured
        return _result(msg_id, payload)

    # Capabilities we never advertised. Returning empty beats an error code:
    # some clients probe these regardless and log the failure as a defect.
    if method in ("resources/list", "resources/templates/list"):
        return _result(msg_id, {"resources": [], "resourceTemplates": []})
    if method == "prompts/list":
        return _result(msg_id, {"prompts": []})

    return _error(msg_id, METHOD_NOT_FOUND, f"Method '{method}' is not supported.")


@router.post("/mcp")
@router.post("/mcp/")
async def mcp_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    agent: Agent = Depends(require_agent),
):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(_error(None, PARSE_ERROR, "Body is not valid JSON."),
                            status_code=200)

    ctx = tools.ToolContext(db=db, agent=agent,
                            rate_limiter=request.app.state.rate_limiter)

    # Batching existed in the 2025-03-26 revision and was dropped in 2025-06-18.
    # Accepting an array costs three lines and means a client on either revision
    # works, which is the whole point of being the notification sink for
    # harnesses we do not control.
    batched = isinstance(payload, list)
    messages = payload if batched else [payload]
    responses = [r for r in (_handle(m, ctx) for m in messages) if r is not None]

    headers = {"MCP-Protocol-Version": LATEST_PROTOCOL}
    if not responses:
        # Everything in the body was a notification — nothing to answer.
        return Response(status_code=202, headers=headers)
    return JSONResponse(responses if batched else responses[0], headers=headers)


@router.get("/mcp")
@router.get("/mcp/")
async def mcp_no_stream():
    """Stateless: there is no server-initiated event stream to open."""
    return Response(status_code=405, headers={"Allow": "POST"})


@router.delete("/mcp")
@router.delete("/mcp/")
async def mcp_no_session():
    """Stateless: no session was issued, so there is none to end."""
    return Response(status_code=405, headers={"Allow": "POST"})
