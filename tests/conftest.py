from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_notify.config import Settings
from agent_notify.main import create_app


@pytest.fixture()
def app():
    settings = Settings.from_env(
        database_url="sqlite://",     # in-memory, StaticPool keeps it alive
        admin_password="",            # UI open, as on localhost
        rate_limit_per_minute=10_000, # tests exercising limits override this
    )
    return create_app(settings)


@pytest.fixture()
def client(app):
    # A real loopback peer address: in open mode the server refuses non-loopback
    # peers, and TestClient's default "testclient" pseudo-host would be refused.
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture()
def agent_token(client) -> str:
    r = client.post("/api/v1/agents", json={"name": "yana"})
    assert r.status_code == 201
    return r.json()["token"]


@pytest.fixture()
def auth(agent_token) -> dict:
    return {"Authorization": f"Bearer {agent_token}"}


def notify(client, auth, idempotency_key: str | None = None, **overrides):
    payload = {
        "type": "input.needed",
        "category": "attention",
        "priority": "high",
        "title": "Which entity paid the Meridian invoice?",
        "body": "Inc or LTD — needed to issue the correct invoice.",
        "group_key": "PROJ-182",
    }
    payload.update(overrides)
    headers = dict(auth)
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return client.post("/api/v1/notifications", json=payload, headers=headers)
