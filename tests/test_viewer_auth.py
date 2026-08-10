"""Viewer auth: the cookie-or-viewer-token gate on read/triage endpoints.

The contract under test: with ADMIN_PASSWORD set, a session cookie and a
viewer token are each sufficient; an agent token is not — write identity must
never grant read access. With no password, everything stays open (localhost
mode).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from agent_notify.auth import (
    SESSION_COOKIE,
    VIEWER_TOKEN_PREFIX,
    _session_signature,
    generate_token,
    hash_token,
)
from agent_notify.config import Settings
from agent_notify.db.models import ViewerToken
from agent_notify.main import create_app

PASSWORD = "hunter2"


@pytest.fixture()
def app():
    settings = Settings.from_env(
        database_url="sqlite://",
        admin_password=PASSWORD,
        rate_limit_per_minute=10_000,
    )
    return create_app(settings)


@pytest.fixture()
def client(app):
    # Cookies off by default so each test opts into its credential explicitly.
    return TestClient(app)


def make_viewer_token(app) -> str:
    token = generate_token(VIEWER_TOKEN_PREFIX)
    with app.state.session_factory() as db:
        db.add(ViewerToken(label="test-device", token_hash=hash_token(token)))
        db.commit()
    return token


def make_agent_token(app) -> str:
    """Register an agent through the API using a cookie session."""
    with TestClient(app) as signed_in:
        r = signed_in.post("/api/v1/session", json={"password": PASSWORD})
        assert r.status_code == 204
        r = signed_in.post("/api/v1/agents", json={"name": "writer"})
        assert r.status_code == 201
        return r.json()["token"]


def test_feed_rejects_anonymous(client):
    assert client.get("/api/v1/notifications").status_code == 401


def test_session_cookie_grants_access(client):
    r = client.post("/api/v1/session", json={"password": PASSWORD})
    assert r.status_code == 204
    assert client.get("/api/v1/notifications").status_code == 200
    assert client.get("/api/v1/notifications/facets").status_code == 200


def test_viewer_token_grants_access(app, client):
    token = make_viewer_token(app)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/notifications", headers=headers).status_code == 200
    assert client.get("/api/v1/notifications/facets", headers=headers).status_code == 200


def test_viewer_token_updates_last_used(app, client):
    token = make_viewer_token(app)
    client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {token}"})
    with app.state.session_factory() as db:
        row = db.query(ViewerToken).filter_by(label="test-device").one()
        assert row.last_used_at is not None


def test_agent_token_cannot_read(app, client):
    """Write identity must not grant read access."""
    agent_token = make_agent_token(app)
    r = client.get("/api/v1/notifications",
                   headers={"Authorization": f"Bearer {agent_token}"})
    assert r.status_code == 401
    # ...while the same token still writes fine.
    r = client.post("/api/v1/notifications",
                    headers={"Authorization": f"Bearer {agent_token}"},
                    json={"type": "job.done", "title": "hi"})
    assert r.status_code in (200, 201)


def test_unknown_and_revoked_viewer_tokens_rejected(app, client):
    bogus = generate_token(VIEWER_TOKEN_PREFIX)
    assert client.get("/api/v1/notifications",
                      headers={"Authorization": f"Bearer {bogus}"}).status_code == 401

    token = make_viewer_token(app)
    with app.state.session_factory() as db:
        db.query(ViewerToken).filter_by(label="test-device").delete()
        db.commit()
    assert client.get("/api/v1/notifications",
                      headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_no_password_stays_open():
    settings = Settings.from_env(database_url="sqlite://", admin_password="")
    client = TestClient(create_app(settings), client=("127.0.0.1", 50000))
    assert client.get("/api/v1/notifications").status_code == 200


# --- agent management is admin-only ----------------------------------------------
#
# The escalation that must not exist: a viewer token is a device credential
# (menu-bar app, cron), and if it could create or rotate agents it could mint
# itself a write token. Only the password session manages agents.


def test_viewer_token_cannot_manage_agents(app, client):
    token = make_viewer_token(app)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/agents", headers=headers).status_code == 200
    r = client.post("/api/v1/agents", json={"name": "sneaky"}, headers=headers)
    assert r.status_code == 403
    make_agent_token(app)  # registers slug "writer"
    assert client.post("/api/v1/agents/writer/token", headers=headers).status_code == 403
    assert client.delete("/api/v1/agents/writer", headers=headers).status_code == 403


def test_anonymous_cannot_manage_agents(client):
    assert client.post("/api/v1/agents", json={"name": "x"}).status_code == 401


def test_session_manages_agents(client):
    assert client.post("/api/v1/session", json={"password": PASSWORD}).status_code == 204
    assert client.post("/api/v1/agents", json={"name": "ok"}).status_code == 201


def test_viewer_token_cannot_write(app, client):
    """The converse of test_agent_token_cannot_read: read identity must not post."""
    token = make_viewer_token(app)
    r = client.post("/api/v1/notifications",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"type": "job.done", "title": "hi"})
    assert r.status_code == 401


# --- session cookie properties ----------------------------------------------------


def test_session_cookie_bound_to_install():
    """The signing secret is per-install: a cookie captured from one deployment
    is worthless against another, even with the same password."""
    def make():
        settings = Settings.from_env(database_url="sqlite://", admin_password=PASSWORD)
        return TestClient(create_app(settings))

    a, b = make(), make()
    assert a.post("/api/v1/session", json={"password": PASSWORD}).status_code == 204
    b.cookies.set(SESSION_COOKIE, a.cookies[SESSION_COOKIE])
    assert a.get("/api/v1/notifications").status_code == 200
    assert b.get("/api/v1/notifications").status_code == 401


def test_expired_session_cookie_rejected(app, client):
    past = int(time.time()) - 10
    stale = f"{past}.{_session_signature(app.state.session_secret, PASSWORD, past)}"
    client.cookies.set(SESSION_COOKIE, stale)
    assert client.get("/api/v1/notifications").status_code == 401


def test_garbage_session_cookie_is_401_not_500(client):
    for cookie in ("nonsense", "123", ".", "99999999999999999999.sig"):
        client.cookies.set(SESSION_COOKIE, cookie)
        assert client.get("/api/v1/notifications").status_code == 401, cookie


# --- login throttling -------------------------------------------------------------


def test_login_is_rate_limited(client):
    codes = [client.post("/api/v1/session", json={"password": "wrong"}).status_code
             for _ in range(8)]
    assert codes[0] == 401
    assert 429 in codes
    # The bucket throttles attempts, not just failures — the right password
    # gets no free pass once the client is over the limit.
    assert client.post("/api/v1/session",
                       json={"password": PASSWORD}).status_code == 429
