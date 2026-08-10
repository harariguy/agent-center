"""Authentication: bearer tokens for agents, an optional session for the UI.

Agent tokens are 256-bit random values stored as sha256 hashes — a fast hash is
correct here (slow hashes exist to protect low-entropy secrets; these are not
guessable). The raw token is shown exactly once, at creation.

UI auth is deliberately minimal for a self-hosted tool: with no ADMIN_PASSWORD
set the server binds to localhost and the UI is open; setting it enables a
login that issues a signed, expiring session cookie. No users table, no JWT.

The cookie is `expiry.HMAC(secret, expiry + password-digest)`, where the secret
is random and per-install (created on first boot, kept in the database so
serverless instances agree on it). Each piece earns its place: the random
secret means a captured cookie cannot be cracked offline into the password;
the embedded expiry means a stolen cookie dies on its own instead of living
for the life of the password; the password digest means changing the password
still invalidates every session at once. Deleting the `session_secret` row in
`meta` rotates the secret — a global sign-out.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db.models import Agent, Meta, ViewerToken, utcnow
from .errors import problem

TOKEN_PREFIX = "an_"          # agent (write) tokens — greppable in logs and env files
VIEWER_TOKEN_PREFIX = "anv_"  # viewer (read/triage) tokens
SESSION_COOKIE = "agent_notify_session"
SESSION_TTL_SECONDS = 30 * 24 * 3600


def generate_token(prefix: str = TOKEN_PREFIX) -> str:
    return prefix + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def load_session_secret(session_factory) -> str:
    """Get-or-create the per-install cookie-signing secret (module docstring)."""
    with session_factory() as db:
        row = db.get(Meta, "session_secret")
        if row is None:
            row = Meta(key="session_secret", value=secrets.token_hex(32))
            db.add(row)
            try:
                db.commit()
            except Exception:
                # Two instances raced the first boot; the winner's row stands.
                db.rollback()
                row = db.get(Meta, "session_secret")
        return row.value


def _session_signature(secret: str, admin_password: str, expires: int) -> str:
    msg = f"session-v1:{expires}:{hashlib.sha256(admin_password.encode()).hexdigest()}"
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def issue_session_cookie(secret: str, admin_password: str) -> str:
    expires = int(time.time()) + SESSION_TTL_SECONDS
    return f"{expires}.{_session_signature(secret, admin_password, expires)}"


def _session_cookie_valid(request: Request, admin_password: str) -> bool:
    cookie = request.cookies.get(SESSION_COOKIE, "")
    expires_raw, _, signature = cookie.partition(".")
    if not expires_raw.isdigit():
        return False  # absent, malformed, or a pre-0.1 cookie — never a 500
    expires = int(expires_raw)
    if expires < time.time():
        return False
    expected = _session_signature(request.app.state.session_secret,
                                  admin_password, expires)
    # Compare as bytes: compare_digest raises on non-ASCII str, and the cookie
    # header is attacker-controlled — a crafted byte must mean 401, not 500.
    return hmac.compare_digest(signature.encode(), expected.encode())


def get_db(request: Request):
    factory = request.app.state.session_factory
    db = factory()
    try:
        yield db
    finally:
        db.close()


def require_agent(request: Request, db: Session = Depends(get_db)) -> Agent:
    """Resolve the calling agent from its bearer token, or 401."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise problem(401, "Missing bearer token",
                      "Send `Authorization: Bearer <agent-token>`.")
    agent = db.scalar(select(Agent).where(Agent.token_hash == hash_token(token.strip())))
    if agent is None:
        raise problem(401, "Unknown token", "This token does not match any agent.")
    agent.last_seen_at = utcnow()
    db.commit()
    return agent


def require_viewer(request: Request, db: Session = Depends(get_db)) -> None:
    """Gate viewer endpoints when ADMIN_PASSWORD is set; open on localhost default.

    Two credentials, because there are two kinds of caller: humans sign in with
    the password and carry a session cookie; programs that have no browser
    session (a retention cron, a script) send a viewer token. Agent tokens are
    deliberately rejected here — they are write-only identity, and an agent
    must not be able to read the feed just because it can post to it.
    """
    password = request.app.state.settings.admin_password
    if not password:
        return
    if _session_cookie_valid(request, password):
        return
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip().startswith(VIEWER_TOKEN_PREFIX):
        viewer = db.scalar(select(ViewerToken)
                           .where(ViewerToken.token_hash == hash_token(token.strip())))
        if viewer is not None:
            viewer.last_used_at = utcnow()
            db.commit()
            return
    raise problem(401, "Not signed in",
                  "POST /api/v1/session with the admin password, or send "
                  "`Authorization: Bearer <viewer-token>` (created with "
                  "`agent-notify viewer add`).")


def require_admin(request: Request) -> None:
    """Gate agent management when ADMIN_PASSWORD is set; open on localhost default.

    Stricter than `require_viewer`, and the difference is the point: a viewer
    token is a device credential (a menu-bar app, a retention cron) and must
    stay read/triage-only. If it could mint or rotate agent tokens, stealing
    one would escalate read access into write access. Only the password
    session manages agents.
    """
    password = request.app.state.settings.admin_password
    if not password:
        return
    if _session_cookie_valid(request, password):
        return
    raise problem(403, "Admin session required",
                  "Managing agents needs the admin password session "
                  "(POST /api/v1/session). Viewer tokens read and triage only.")
