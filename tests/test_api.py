"""API contract: auth, validation shape, pagination, filters, hardening."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from agent_center.config import Settings
from agent_center.main import create_app

from .conftest import notify


def test_ingest_requires_token(client):
    r = client.post("/api/v1/notifications", json={"type": "x", "title": "y"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


def test_unknown_token_rejected(client):
    r = client.post("/api/v1/notifications", json={"type": "x", "title": "y"},
                    headers={"Authorization": "Bearer an_nope"})
    assert r.status_code == 401


def test_validation_error_is_problem_json(client, auth):
    r = client.post("/api/v1/notifications", json={"type": "Bad Type!", "title": ""},
                    headers=auth)
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert any("type" in e["loc"] for e in r.json()["errors"])


def test_request_id_echoed(client):
    r = client.get("/api/v1/healthz", headers={"X-Request-Id": "trace-me"})
    assert r.headers["x-request-id"] == "trace-me"


def test_body_cap(client, auth):
    r = client.post("/api/v1/notifications", content=b"x" * 100_000,
                    headers={**auth, "Content-Type": "application/json"})
    assert r.status_code == 413


def test_chunked_body_rejected(client, auth):
    # A chunked body declares no length, so the cap above could not bound it —
    # and FastAPI buffers the body before auth runs. Refused outright.
    def stream():
        yield b'{"type": "job.done", "title": "hi"}'

    r = client.post("/api/v1/notifications", content=stream(),
                    headers={**auth, "Content-Type": "application/json"})
    assert r.status_code == 411


def test_overlong_idempotency_key_rejected(client, auth):
    r = notify(client, auth, idempotency_key="k" * 201)
    assert r.status_code == 422


def test_rate_limit():
    settings = Settings.from_env(database_url="sqlite://", admin_password="",
                                 rate_limit_per_minute=3)
    client = TestClient(create_app(settings), client=("127.0.0.1", 50000))
    token = client.post("/api/v1/agents", json={"name": "chatty"}).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    codes = [notify(client, auth, group_key=f"K-{i}").status_code for i in range(5)]
    assert 429 in codes
    assert codes[0] in (200, 201)


# --- feed ----------------------------------------------------------------------


def test_feed_orders_newest_first_and_paginates(client, auth):
    for i in range(7):
        notify(client, auth, group_key=f"T-{i}", title=f"item {i}")
    page1 = client.get("/api/v1/notifications?limit=4").json()
    assert len(page1["items"]) == 4
    assert page1["next_cursor"]
    page2 = client.get(f"/api/v1/notifications?limit=4&cursor={page1['next_cursor']}").json()
    ids = [n["id"] for n in page1["items"] + page2["items"]]
    assert len(ids) == len(set(ids)) == 7
    assert page2["next_cursor"] is None


def test_cursor_stable_across_inserts(client, auth):
    for i in range(4):
        notify(client, auth, group_key=f"S-{i}")
    page1 = client.get("/api/v1/notifications?limit=2").json()
    notify(client, auth, group_key="S-new")      # lands at the top, not in page 2
    page2 = client.get(f"/api/v1/notifications?limit=2&cursor={page1['next_cursor']}").json()
    overlap = {n["id"] for n in page1["items"]} & {n["id"] for n in page2["items"]}
    assert not overlap


def test_bad_cursor_is_400(client):
    r = client.get("/api/v1/notifications?cursor=garbage!!!")
    assert r.status_code == 400


def test_priority_order_paginates_by_severity_then_recency(client, auth):
    notify(client, auth, group_key="normal", priority="normal")
    notify(client, auth, group_key="urgent-old", priority="urgent")
    notify(client, auth, group_key="high", priority="high")
    notify(client, auth, group_key="urgent-new", priority="urgent")

    page1 = client.get("/api/v1/notifications?order=priority&limit=2").json()
    assert [n["group_key"] for n in page1["items"]] == ["urgent-new", "urgent-old"]
    page2 = client.get(
        f"/api/v1/notifications?order=priority&limit=2&cursor={page1['next_cursor']}"
    ).json()
    assert [n["group_key"] for n in page2["items"]] == ["high", "normal"]
    assert page2["next_cursor"] is None


def test_filters(client, auth):
    notify(client, auth, group_key="A", category="attention")
    notify(client, auth, group_key="B", category="activity", type="pr.opened",
           priority="low", title="Opened PR #7")
    attention = client.get("/api/v1/notifications?category=attention").json()["items"]
    assert {n["group_key"] for n in attention} == {"A"}
    by_type = client.get("/api/v1/notifications?type=pr.opened").json()["items"]
    assert {n["group_key"] for n in by_type} == {"B"}
    search = client.get("/api/v1/notifications?q=meridian").json()["items"]
    assert {n["group_key"] for n in search} == {"A"}


def test_filter_by_source_app_and_tag(client, auth):
    notify(client, auth, group_key="A", source={"app": "linear"}, tags=["billing"])
    notify(client, auth, group_key="B", source={"app": "github"}, tags=["ci"])
    by_app = client.get("/api/v1/notifications?source_app=linear").json()["items"]
    assert {n["group_key"] for n in by_app} == {"A"}
    by_tag = client.get("/api/v1/notifications?tag=ci").json()["items"]
    assert {n["group_key"] for n in by_tag} == {"B"}


def test_facets_enumerate_filterable_values(client, auth):
    notify(client, auth, group_key="A", category="attention",
           source={"app": "linear"}, tags=["billing", "urgent-review"])
    notify(client, auth, group_key="B", category="activity", type="pr.opened",
           priority="low", source={"app": "github"}, tags=["billing"])
    read = notify(client, auth, group_key="C", category="activity").json()
    client.post(f"/api/v1/notifications/{read['id']}/read")

    f = client.get("/api/v1/notifications/facets").json()
    assert [a["value"] for a in f["agents"]] == ["yana"]
    assert f["agents"][0]["label"] == "yana" and f["agents"][0]["count"] == 3
    assert {t["value"] for t in f["types"]} == {"input.needed", "pr.opened"}
    assert {p["value"] for p in f["priorities"]} == {"high", "low"}
    assert {s["value"] for s in f["source_apps"]} == {"linear", "github"}
    # tags fold across rows, most-used first
    assert next(t["value"] for t in f["tags"]) == "billing"
    assert {t["value"]: t["count"] for t in f["tags"]}["billing"] == 2
    assert f["counts"] == {"total": 3, "unread": 2, "attention": 1,
                           "attention_unread": 1, "activity": 2, "activity_unread": 1}


def test_facets_follow_archive_scope(client, auth):
    live = notify(client, auth, group_key="A", source={"app": "linear"}).json()
    notify(client, auth, group_key="B", source={"app": "github"})
    client.post(f"/api/v1/notifications/{live['id']}/archive")

    live_facets = client.get("/api/v1/notifications/facets").json()
    assert {s["value"] for s in live_facets["source_apps"]} == {"github"}
    archived = client.get("/api/v1/notifications/facets?archived=true").json()
    assert {s["value"] for s in archived["source_apps"]} == {"linear"}
    assert archived["counts"]["total"] == 1


def test_facets_empty_feed(client):
    f = client.get("/api/v1/notifications/facets").json()
    assert f["agents"] == f["types"] == f["tags"] == []
    assert f["counts"]["total"] == 0


def test_unread_filter_and_read_all(client, auth):
    a = notify(client, auth, group_key="A").json()
    notify(client, auth, group_key="B")
    client.post(f"/api/v1/notifications/{a['id']}/read")
    unread = client.get("/api/v1/notifications?unread=true").json()["items"]
    assert {n["group_key"] for n in unread} == {"B"}
    client.post("/api/v1/notifications/read-all")
    assert client.get("/api/v1/notifications?unread=true").json()["items"] == []


def test_read_all_respects_current_filters(client, auth):
    attention = notify(client, auth, group_key="attention", category="attention").json()
    activity = notify(client, auth, group_key="activity", category="activity").json()
    client.post("/api/v1/notifications/read-all?category=attention")

    assert client.get(f"/api/v1/notifications/{attention['id']}").json()["read_at"]
    assert client.get(f"/api/v1/notifications/{activity['id']}").json()["read_at"] is None


def test_archived_hidden_by_default(client, auth):
    n = notify(client, auth).json()
    client.post(f"/api/v1/notifications/{n['id']}/archive")
    assert client.get("/api/v1/notifications").json()["items"] == []
    archived = client.get("/api/v1/notifications?archived=true").json()["items"]
    assert [x["id"] for x in archived] == [n["id"]]


def test_archived_notification_can_be_restored(client, auth):
    n = notify(client, auth).json()
    client.post(f"/api/v1/notifications/{n['id']}/archive")

    restored = client.post(f"/api/v1/notifications/{n['id']}/unarchive")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert [x["id"] for x in client.get("/api/v1/notifications").json()["items"]] == [n["id"]]


def test_snooze_hides_notification_and_refire_wakes_it(client, auth):
    n = notify(client, auth, group_key="sleepy").json()
    until = datetime.now(UTC) + timedelta(days=1)
    snoozed = client.post(
        f"/api/v1/notifications/{n['id']}/snooze",
        json={"until": until.isoformat()},
    )
    assert snoozed.status_code == 200
    assert snoozed.json()["snoozed_until"]
    assert client.get("/api/v1/notifications").json()["items"] == []
    assert client.get("/api/v1/notifications/facets").json()["counts"]["total"] == 0

    notify(client, auth, group_key="sleepy")
    visible = client.get("/api/v1/notifications").json()["items"]
    assert [x["id"] for x in visible] == [n["id"]]
    assert visible[0]["snoozed_until"] is None


def test_detail_includes_history(client, auth):
    n = notify(client, auth).json()
    notify(client, auth)
    detail = client.get(f"/api/v1/notifications/{n['id']}").json()
    assert len(detail["history"]) == 2
    assert detail["history"][0]["payload_json"]["title"]


# --- agents ---------------------------------------------------------------------


def test_agent_lifecycle(client):
    created = client.post("/api/v1/agents", json={"name": "My Bot!"}).json()
    assert created["slug"] == "my-bot"
    assert created["token"].startswith("an_")
    dup = client.post("/api/v1/agents", json={"name": "My Bot!"})
    assert dup.status_code == 409
    assert client.delete("/api/v1/agents/my-bot").status_code == 204
    # revoked token no longer authenticates
    r = client.post("/api/v1/notifications",
                    json={"type": "x.y", "title": "hi"},
                    headers={"Authorization": f"Bearer {created['token']}"})
    assert r.status_code == 401


def test_token_rotation_replaces_the_credential_and_keeps_history(client, auth, agent_token):
    notify(client, auth)
    rotated = client.post("/api/v1/agents/yana/token")
    assert rotated.status_code == 200
    new_token = rotated.json()["token"]
    assert new_token != agent_token

    # The old token is dead, the new one works, the notifications stay put.
    assert notify(client, {"Authorization": f"Bearer {agent_token}"}).status_code == 401
    assert notify(client, {"Authorization": f"Bearer {new_token}"},
                  group_key="PROJ-999").status_code == 201
    assert len(client.get("/api/v1/notifications").json()["items"]) == 2


def test_rotating_revives_a_revoked_agent(client):
    created = client.post("/api/v1/agents", json={"name": "paused"}).json()
    client.delete("/api/v1/agents/paused")
    token = client.post("/api/v1/agents/paused/token").json()["token"]
    assert client.post("/api/v1/notifications", json={"type": "x.y", "title": "back"},
                       headers={"Authorization": f"Bearer {token}"}).status_code == 201
    assert created["token"] != token


def test_rotating_an_unknown_agent_is_404(client):
    assert client.post("/api/v1/agents/ghost/token").status_code == 404


# --- UI auth --------------------------------------------------------------------


def test_admin_password_gates_feed():
    settings = Settings.from_env(database_url="sqlite://", admin_password="s3cret")
    client = TestClient(create_app(settings))
    assert client.get("/api/v1/notifications").status_code == 401
    assert client.post("/api/v1/session", json={"password": "wrong"}).status_code == 401
    login = client.post("/api/v1/session", json={"password": "s3cret"})
    assert login.status_code == 204
    assert client.get("/api/v1/notifications").status_code == 200


# --- fail-closed exposure check ---------------------------------------------------


def test_public_bind_without_password_refuses():
    import pytest

    settings = Settings.from_env(database_url="sqlite://", host="0.0.0.0")
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        create_app(settings)


def test_vercel_env_counts_as_public(monkeypatch):
    import pytest

    monkeypatch.setenv("VERCEL", "1")
    settings = Settings.from_env(database_url="sqlite://")  # loopback host
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        create_app(settings)


def test_public_bind_allowed_with_password_or_optout():
    with_password = Settings.from_env(
        database_url="sqlite://", host="0.0.0.0", admin_password="x")
    create_app(with_password)

    opted_out = Settings.from_env(
        database_url="sqlite://", host="0.0.0.0", allow_insecure_bind=True)
    create_app(opted_out)


def test_open_mode_refuses_nonlocal_peers():
    """The startup check can't see the real bind (`uvicorn --factory --host
    0.0.0.0` never sets HOST) — the request-time guard is what holds there."""
    settings = Settings.from_env(database_url="sqlite://", admin_password="")
    client = TestClient(create_app(settings), client=("203.0.113.9", 4711))
    assert client.get("/api/v1/notifications").status_code == 403
    assert client.get("/api/v1/healthz").status_code == 403


def test_open_mode_serves_loopback_peers():
    settings = Settings.from_env(database_url="sqlite://", admin_password="")
    for host in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        client = TestClient(create_app(settings), client=(host, 4711))
        assert client.get("/api/v1/notifications").status_code == 200, host


def test_password_mode_serves_nonlocal_peers():
    settings = Settings.from_env(database_url="sqlite://", admin_password="x")
    client = TestClient(create_app(settings), client=("203.0.113.9", 4711))
    # Reachable — auth applies instead of the refusal.
    assert client.get("/api/v1/notifications").status_code == 401


def test_insecure_bind_optout_serves_nonlocal_peers():
    settings = Settings.from_env(
        database_url="sqlite://", admin_password="", allow_insecure_bind=True)
    client = TestClient(create_app(settings), client=("203.0.113.9", 4711))
    assert client.get("/api/v1/notifications").status_code == 200


# --- /facets ETag ------------------------------------------------------------------


def test_facets_etag_roundtrip(client, auth):
    from .conftest import notify

    notify(client, auth)
    first = client.get("/api/v1/notifications/facets")
    assert first.status_code == 200
    etag = first.headers["etag"]

    unchanged = client.get("/api/v1/notifications/facets",
                           headers={"If-None-Match": etag})
    assert unchanged.status_code == 304

    notify(client, auth, group_key="OTHER-1", title="something else")
    changed = client.get("/api/v1/notifications/facets",
                         headers={"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag


def test_facets_etag_changes_when_unread_group_refires(client, auth):
    from .conftest import notify

    first_fire = notify(client, auth)
    assert first_fire.status_code == 201
    facets = client.get("/api/v1/notifications/facets")
    etag = facets.headers["etag"]

    refire = notify(client, auth, body="A newer occurrence with unchanged facets.")
    assert refire.status_code == 200
    assert refire.json()["occurrences"] == 2

    changed = client.get(
        "/api/v1/notifications/facets",
        headers={"If-None-Match": etag},
    )
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag
