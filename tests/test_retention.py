"""Retention prune: old notifications (and their occurrences) go, recent stay."""

from __future__ import annotations

from datetime import timedelta

from agent_notifications.core.retention import prune
from agent_notifications.db.models import Notification, Occurrence, utcnow

from .conftest import notify


def backdate(app, notification_id: str, days: int) -> None:
    with app.state.session_factory() as db:
        n = db.get(Notification, notification_id)
        n.last_seen_at = utcnow() - timedelta(days=days)
        db.commit()


def test_prune_deletes_old_with_occurrences(app, client, auth):
    old = notify(client, auth, group_key="OLD-1").json()["id"]
    fresh = notify(client, auth, group_key="NEW-1").json()["id"]
    backdate(app, old, days=120)

    with app.state.session_factory() as db:
        assert prune(db, retention_days=90) == 1
        assert db.get(Notification, old) is None
        assert db.get(Notification, fresh) is not None
        assert db.query(Occurrence).filter_by(notification_id=old).count() == 0
        assert db.query(Occurrence).filter_by(notification_id=fresh).count() == 1


def test_prune_zero_disables(app, client, auth):
    nid = notify(client, auth).json()["id"]
    backdate(app, nid, days=1000)
    with app.state.session_factory() as db:
        assert prune(db, retention_days=0) == 0
        assert db.get(Notification, nid) is not None


def test_prune_endpoint(app, client, auth):
    nid = notify(client, auth).json()["id"]
    backdate(app, nid, days=120)
    r = client.post("/api/v1/prune")
    assert r.status_code == 200
    assert r.json() == {"deleted": 1}
    # GET works too — Vercel Cron can only GET.
    assert client.get("/api/v1/prune").status_code == 200


def test_prune_endpoint_requires_viewer_auth():
    from fastapi.testclient import TestClient

    from agent_notifications.config import Settings
    from agent_notifications.main import create_app

    settings = Settings.from_env(database_url="sqlite://", admin_password="x")
    locked = TestClient(create_app(settings))
    assert locked.post("/api/v1/prune").status_code == 401
