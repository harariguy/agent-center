"""UI login — only meaningful when ADMIN_PASSWORD is set."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from ..auth import SESSION_COOKIE, SESSION_TTL_SECONDS, issue_session_cookie
from ..errors import problem

router = APIRouter(prefix="/api/v1/session", tags=["session"])

# The admin password is the one human-chosen (guessable) secret in the system,
# which makes login the one endpoint worth throttling per client: a token
# bucket turns an online dictionary attack from wire speed into a few guesses
# a minute. Not env-configurable on purpose — there is no good reason to raise it.
LOGIN_ATTEMPTS_PER_MINUTE = 5


class LoginIn(BaseModel):
    password: str


@router.post("", status_code=204)
def login(data: LoginIn, request: Request, response: Response):
    password = request.app.state.settings.admin_password
    if not password:
        return Response(status_code=204)  # auth disabled; nothing to do
    client = request.scope.get("client")
    if not request.app.state.login_rate_limiter.allow(client[0] if client else "local"):
        raise problem(429, "Too many attempts", "Wait a minute and try again.")
    # Compare as bytes: compare_digest raises on non-ASCII str, and both a
    # non-ASCII configured password and a crafted guess must mean 401, not 500.
    if not hmac.compare_digest(data.password.encode(), password.encode()):
        raise problem(401, "Wrong password", "")
    response.status_code = 204
    response.set_cookie(
        SESSION_COOKIE,
        issue_session_cookie(request.app.state.session_secret, password),
        httponly=True, samesite="lax", max_age=SESSION_TTL_SECONDS,
        # Mirror the scheme the request arrived on: an https deploy gets a
        # cookie the browser will never send over plain http; localhost and
        # tailnet http deployments still work.
        secure=request.url.scheme == "https",
    )
    return response


@router.delete("", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return Response(status_code=204)
