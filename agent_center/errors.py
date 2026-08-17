"""RFC 7807 problem+json errors — one error shape everywhere."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_TYPE = "application/problem+json"


def problem(status: int, title: str, detail: str = "") -> HTTPException:
    """An HTTPException whose detail carries the problem document."""
    return HTTPException(status_code=status, detail={"title": title, "detail": detail})


def _render(request: Request, status: int, title: str, detail, extra: dict | None = None):
    doc = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": str(request.url.path),
    }
    if extra:
        doc.update(extra)
    return JSONResponse(doc, status_code=status, media_type=PROBLEM_TYPE)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            return _render(request, exc.status_code,
                           detail.get("title", "Error"), detail.get("detail", ""))
        return _render(request, exc.status_code, str(detail), "")

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return _render(
            request, 422, "Validation failed",
            "One or more fields are invalid.",
            {"errors": [
                {"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]}
                for e in exc.errors()
            ]},
        )
