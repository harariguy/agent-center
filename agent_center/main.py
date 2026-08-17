"""App factory: routers, middleware, error shape, static UI."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, agents, notifications, session
from .auth import load_session_secret
from .config import Settings
from .core.ratelimit import RateLimiter
from .core.retention import prune
from .db.session import init_db, make_engine, make_session_factory
from .docs import GUIDE, skill
from .errors import PROBLEM_TYPE, install_handlers
from .mcp import router as mcp_router

log = logging.getLogger("agent_center")

STATIC_DIR = Path(__file__).parent / "static"

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


class LazyStaticFiles(StaticFiles):
    """StaticFiles for a directory that may not exist yet.

    The UI can be built *after* the server starts (`pnpm build` against a
    running dev install). Plain StaticFiles stats the directory on first
    request and answers 500 until a restart; this answers 404 while the
    directory is missing and starts serving the moment the files land.
    """

    async def __call__(self, scope, receive, send):
        if self.config_checked or Path(self.directory).is_dir():
            await super().__call__(scope, receive, send)
        else:
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)


def _check_exposure(settings: Settings) -> None:
    """Refuse to build a publicly reachable app with no auth — fail closed.

    This is the startup half: fast, loud feedback when HOST says the bind is
    public. It cannot see the real bind address — `uvicorn --factory --host
    0.0.0.0` never sets HOST — so the per-request loopback guard in
    `create_app` is what actually holds the line; this check just fails early
    for the paths that can be caught early. Serverless platforms have no bind
    address at all, so the Vercel marker env counts as public exposure.
    """
    if settings.admin_password or settings.allow_insecure_bind:
        return
    exposed = settings.host not in LOOPBACK_HOSTS or os.environ.get("VERCEL")
    if exposed:
        raise RuntimeError(
            "Refusing to start: the server would be reachable beyond localhost "
            "with no authentication. Set ADMIN_PASSWORD to enable the login and "
            "viewer tokens, or set ALLOW_INSECURE_BIND=1 if this deployment is "
            "already protected (tailnet, authenticating reverse proxy)."
        )


def _is_loopback(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False  # unparseable peer — fail closed
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped  # dual-stack sockets report ::ffff:127.0.0.1
    return addr.is_loopback


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    _check_exposure(settings)

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    def _prune_once() -> None:
        with session_factory() as db:
            deleted = prune(db, settings.retention_days)
        if deleted:
            log.info("retention: pruned %d notifications older than %d days",
                     deleted, settings.retention_days)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Startup prune + daily loop covers long-running deploys. Serverless
        # instances freeze between requests, so they use POST /api/v1/prune
        # from an external cron instead; this loop is merely harmless there.
        async def daily():
            while True:
                await asyncio.sleep(24 * 3600)
                await asyncio.to_thread(_prune_once)

        await asyncio.to_thread(_prune_once)
        task = asyncio.create_task(daily())
        yield
        task.cancel()

    app = FastAPI(
        title="Agent Center",
        version="0.1.0",
        description="A notification-only layer for AI agents: they report, you read and "
                    "click out. It does not run agents, hold conversations, or replace "
                    "any channel.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.rate_limiter = RateLimiter(per_minute=settings.rate_limit_per_minute)
    app.state.login_rate_limiter = RateLimiter(per_minute=session.LOGIN_ATTEMPTS_PER_MINUTE)
    init_db(app.state.engine)
    app.state.session_secret = load_session_secret(session_factory)

    install_handlers(app)

    # The request-time half of the exposure check (see _check_exposure): in
    # open mode — no password, no explicit opt-out — only loopback peers are
    # served, whatever address the server actually bound. A `client` of None
    # is a transport that is local by construction (unix socket, in-process).
    open_mode = not settings.admin_password and not settings.allow_insecure_bind

    @app.middleware("http")
    async def refuse_nonlocal_when_open(request: Request, call_next):
        client = request.scope.get("client")
        if open_mode and client is not None and not _is_loopback(client[0]):
            return JSONResponse(
                {"type": "about:blank", "title": "Not available beyond localhost",
                 "status": 403,
                 "detail": "This server has no ADMIN_PASSWORD set, so it only "
                           "answers loopback requests. Set ADMIN_PASSWORD to "
                           "serve beyond localhost, or ALLOW_INSECURE_BIND=1 if "
                           "this deployment is already protected (tailnet, "
                           "authenticating reverse proxy)."},
                status_code=403, media_type=PROBLEM_TYPE,
            )
        return await call_next(request)

    @app.middleware("http")
    async def request_id_and_limits(request: Request, call_next):
        # Body cap before any parsing — a public ingest endpoint must bound its
        # input, and FastAPI buffers the whole body before auth ever runs. A
        # declared Content-Length is trustworthy (uvicorn rejects mismatched
        # lengths), but a chunked body declares nothing, so it is refused
        # outright rather than trusted to stay small.
        length = request.headers.get("content-length")
        if length is None and "chunked" in request.headers.get("transfer-encoding", "").lower():
            return JSONResponse(
                {"type": "about:blank", "title": "Length required", "status": 411,
                 "detail": "Chunked bodies are not accepted; send a Content-Length."},
                status_code=411, media_type=PROBLEM_TYPE,
            )
        if length and int(length) > settings.max_body_bytes:
            return JSONResponse(
                {"type": "about:blank", "title": "Payload too large", "status": 413,
                 "detail": f"Bodies are limited to {settings.max_body_bytes} bytes."},
                status_code=413, media_type=PROBLEM_TYPE,
            )
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    app.include_router(notifications.router)
    app.include_router(agents.router)
    app.include_router(session.router)
    app.include_router(admin.router)
    # Remote MCP, same process and same port: one URL for every harness.
    app.include_router(mcp_router)

    @app.get("/api/v1/healthz", tags=["meta"])
    def healthz():
        return {"status": "ok"}

    # The usage contract, ungated: it carries no secrets, and an agent being set
    # up by hand needs to be able to fetch it before it holds a token.
    @app.get("/api/v1/guide.md", tags=["meta"], response_class=PlainTextResponse)
    def guide():
        return PlainTextResponse(GUIDE, media_type="text/markdown; charset=utf-8")

    # The installable skill, also ungated. An agent fetches this during setup and
    # writes it into its own harness's skill directory — which is what turns
    # notifying from something it does when asked into something it does by habit.
    @app.get("/api/v1/skill.md", tags=["meta"], response_class=PlainTextResponse)
    def skill_md(request: Request):
        return PlainTextResponse(skill(str(request.base_url)),
                                 media_type="text/markdown; charset=utf-8")

    @app.get("/llms.txt", include_in_schema=False, response_class=PlainTextResponse)
    def llms_txt():
        return PlainTextResponse(GUIDE, media_type="text/plain; charset=utf-8")

    # --- static UI (the React app in frontend/, built into static/) ----------

    # Mounted unconditionally (see LazyStaticFiles): the `/` route below
    # already checks index.html per request, and the asset mount must agree —
    # a page whose bundles 404 until a restart is a white screen with no
    # error anywhere the user looks.
    app.mount("/assets",
              LazyStaticFiles(directory=STATIC_DIR / "assets", check_dir=False),
              name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        page = STATIC_DIR / "index.html"
        if page.is_file():
            return FileResponse(page)
        return JSONResponse(
            {"detail": "UI not built; run `pnpm build` in frontend/. The API is at /api/v1."},
            status_code=200,
        )

    return app


# No module-level `app = create_app()`: constructing the app touches the
# filesystem (SQLite home dir), and imports must stay side-effect free — tests
# build their own apps against in-memory databases. For raw uvicorn use:
#   uvicorn agent_center.main:create_app --factory
