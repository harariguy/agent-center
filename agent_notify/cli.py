"""CLI: serve Agent Notify, register agents, manage viewer tokens.

    agent-notify serve
    agent-notify agent add <name>
    agent-notify agent list
    agent-notify viewer add <label>
    agent-notify viewer list
    agent-notify viewer revoke <label>
    agent-notify prune
"""

from __future__ import annotations

import argparse
import socket
import sys

from .config import Settings


def _probe_bind(host: str, port: int) -> str | None:
    """Try binding the address once; return the error message if it fails.

    uvicorn logs a bind failure but still exits quietly, and any banner we
    printed first becomes the last, lying thing on screen — pointing at a URL
    that belongs to whatever else is squatting the port. So probe before
    printing anything friendly. SO_REUSEADDR mirrors uvicorn's own socket, so
    the probe doesn't false-alarm on TIME_WAIT leftovers.
    """
    try:
        family, _, _, _, addr = socket.getaddrinfo(
            host, port, type=socket.SOCK_STREAM)[0]
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(addr)
    except OSError as exc:
        return exc.strerror or str(exc)
    return None


def _serve(args) -> int:
    import uvicorn

    from .main import create_app

    settings = Settings.from_env(
        **({"host": args.host} if args.host else {}),
        **({"port": args.port} if args.port else {}),
    )
    try:
        app = create_app(settings)
    except RuntimeError as exc:  # fail-closed exposure check
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if bind_error := _probe_bind(settings.host, settings.port):
        print(f"error: cannot listen on {settings.host}:{settings.port} — {bind_error}.\n"
              f"Something else is probably using the port. Pick another with "
              f"`--port <n>` or `PORT=<n>`.", file=sys.stderr)
        return 1
    print(f"Agent Notify → http://{settings.host}:{settings.port}", flush=True)
    print(f"database: {settings.database_url}", flush=True)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    return 0


def _agent_add(args) -> int:
    from .api.agents import slugify
    from .auth import generate_token, hash_token
    from .db.models import Agent
    from .db.session import init_db, make_engine, make_session_factory

    settings = Settings.from_env()
    engine = make_engine(settings.database_url)
    init_db(engine)
    with make_session_factory(engine)() as db:
        from sqlalchemy import select

        slug = slugify(args.name)
        if db.scalar(select(Agent).where((Agent.name == args.name) | (Agent.slug == slug))):
            print(f"error: agent '{args.name}' already exists", file=sys.stderr)
            return 1
        token = generate_token()
        db.add(Agent(name=args.name, slug=slug, token_hash=hash_token(token)))
        db.commit()

    base = f"http://{settings.host}:{settings.port}"
    print(f"agent '{args.name}' registered (slug: {slug})")
    print("\ntoken (shown once — only its hash is stored):\n")
    print(f"  {token}\n")
    print("send a notification:\n")
    print(f"""  curl -X POST {base}/api/v1/notifications \\
    -H "Authorization: Bearer {token}" \\
    -H "Content-Type: application/json" \\
    -d '{{"type": "ticket.created", "category": "activity",
         "title": "Opened PROJ-42 — investigate flaky deploy",
         "source": {{"app": "linear", "link": "https://linear.app/acme/issue/PROJ-42"}}}}'""")
    return 0


def _agent_list(_args) -> int:
    from sqlalchemy import select

    from .db.models import Agent
    from .db.session import init_db, make_engine, make_session_factory

    settings = Settings.from_env()
    engine = make_engine(settings.database_url)
    init_db(engine)
    with make_session_factory(engine)() as db:
        agents = db.scalars(select(Agent).order_by(Agent.created_at)).all()
        if not agents:
            print("no agents registered — run: agent-notify agent add <name>")
            return 0
        for a in agents:
            seen = a.last_seen_at.strftime("%Y-%m-%d %H:%M") if a.last_seen_at else "never"
            print(f"  {a.slug:<24} last seen: {seen}")
    return 0


def _prune(_args) -> int:
    from .core.retention import prune
    from .db.session import init_db, make_engine, make_session_factory

    settings = Settings.from_env()
    engine = make_engine(settings.database_url)
    init_db(engine)
    with make_session_factory(engine)() as db:
        deleted = prune(db, settings.retention_days)
    if settings.retention_days <= 0:
        print("retention disabled (RETENTION_DAYS <= 0); nothing pruned")
    else:
        print(f"pruned {deleted} notification(s) older than {settings.retention_days} days")
    return 0


def _viewer_db():
    from .db.session import init_db, make_engine, make_session_factory

    settings = Settings.from_env()
    engine = make_engine(settings.database_url)
    init_db(engine)
    return make_session_factory(engine)


def _viewer_add(args) -> int:
    from sqlalchemy import select

    from .auth import VIEWER_TOKEN_PREFIX, generate_token, hash_token
    from .db.models import ViewerToken

    with _viewer_db()() as db:
        if db.scalar(select(ViewerToken).where(ViewerToken.label == args.label)):
            print(f"error: viewer token '{args.label}' already exists", file=sys.stderr)
            return 1
        token = generate_token(VIEWER_TOKEN_PREFIX)
        db.add(ViewerToken(label=args.label, token_hash=hash_token(token)))
        db.commit()

    settings = Settings.from_env()
    base = f"http://{settings.host}:{settings.port}"
    print(f"viewer token '{args.label}' created")
    print("\ntoken (shown once — only its hash is stored):\n")
    print(f"  {token}\n")
    print("read the feed, or run retention, without a browser session:\n")
    print(f"  curl -H \"Authorization: Bearer {token}\" \\\n"
          f"    {base}/api/v1/notifications/facets")
    print(f"  curl -X POST -H \"Authorization: Bearer {token}\" {base}/api/v1/prune")
    return 0


def _viewer_list(_args) -> int:
    from sqlalchemy import select

    from .db.models import ViewerToken

    with _viewer_db()() as db:
        tokens = db.scalars(select(ViewerToken).order_by(ViewerToken.created_at)).all()
        if not tokens:
            print("no viewer tokens — run: agent-notify viewer add <label>")
            return 0
        for t in tokens:
            used = t.last_used_at.strftime("%Y-%m-%d %H:%M") if t.last_used_at else "never"
            print(f"  {t.label:<24} last used: {used}")
    return 0


def _viewer_revoke(args) -> int:
    from sqlalchemy import select

    from .db.models import ViewerToken

    with _viewer_db()() as db:
        token = db.scalar(select(ViewerToken).where(ViewerToken.label == args.label))
        if token is None:
            print(f"error: no viewer token labelled '{args.label}'", file=sys.stderr)
            return 1
        # Unlike agents, viewer tokens carry no history — deleting is clean.
        db.delete(token)
        db.commit()
    print(f"viewer token '{args.label}' revoked")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-notify",
                                     description="Notification layer for AI agents — they report, you read.")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the server")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.set_defaults(func=_serve)

    agent = sub.add_parser("agent", help="manage agents")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    add = agent_sub.add_parser("add", help="register an agent, print its token")
    add.add_argument("name")
    add.set_defaults(func=_agent_add)
    lst = agent_sub.add_parser("list", help="list registered agents")
    lst.set_defaults(func=_agent_list)

    viewer = sub.add_parser("viewer", help="manage viewer (read/triage) tokens")
    viewer_sub = viewer.add_subparsers(dest="viewer_command", required=True)
    vadd = viewer_sub.add_parser("add", help="create a viewer token, print it once")
    vadd.add_argument("label")
    vadd.set_defaults(func=_viewer_add)
    vlist = viewer_sub.add_parser("list", help="list viewer tokens")
    vlist.set_defaults(func=_viewer_list)
    vrevoke = viewer_sub.add_parser("revoke", help="revoke a viewer token")
    vrevoke.add_argument("label")
    vrevoke.set_defaults(func=_viewer_revoke)

    prune_cmd = sub.add_parser("prune", help="delete notifications older than RETENTION_DAYS")
    prune_cmd.set_defaults(func=_prune)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
