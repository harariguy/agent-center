"""Grouping, regression semantics and idempotency — the core write path."""

from .conftest import notify


def test_first_fire_creates(client, auth):
    r = notify(client, auth)
    assert r.status_code == 201
    body = r.json()
    assert body["occurrences"] == 1
    assert body["group_key"] == "PROJ-182"


def test_same_group_key_folds(client, auth):
    first = notify(client, auth).json()
    second = notify(client, auth, title="Meridian invoice — still waiting on Inc/LTD")
    assert second.status_code == 200            # grouped, not created
    body = second.json()
    assert body["id"] == first["id"]
    assert body["occurrences"] == 2
    assert body["title"].startswith("Meridian invoice")   # latest fire wins


def test_different_group_keys_stay_separate(client, auth):
    a = notify(client, auth, group_key="PROJ-1").json()
    b = notify(client, auth, group_key="PROJ-2").json()
    assert a["id"] != b["id"]


def test_no_group_key_falls_back_to_fingerprint(client, auth):
    a = notify(client, auth, group_key=None,
               title="Mesh receipts — 7 new today ($311.83)").json()
    b = notify(client, auth, group_key=None,
               title="Mesh receipts — 3 new today ($86.40)").json()
    assert b["id"] == a["id"]
    assert b["occurrences"] == 2


def test_explicit_key_never_matches_fingerprint_group(client, auth):
    a = notify(client, auth, group_key=None, title="Mesh receipts — 7 new today").json()
    b = notify(client, auth, group_key="MESH", title="Mesh receipts — 7 new today").json()
    assert a["id"] != b["id"]


def test_agents_do_not_share_groups(client, auth):
    other_token = client.post("/api/v1/agents", json={"name": "roger"}).json()["token"]
    other = {"Authorization": f"Bearer {other_token}"}
    a = notify(client, auth).json()
    b = notify(client, other).json()
    assert a["id"] != b["id"]


# --- regression semantics -----------------------------------------------------


def test_refire_marks_read_notification_unread(client, auth):
    n = notify(client, auth).json()
    client.post(f"/api/v1/notifications/{n['id']}/read")
    refired = notify(client, auth).json()
    assert refired["id"] == n["id"]
    assert refired["read_at"] is None


def test_refire_on_archived_opens_new_notification(client, auth):
    n = notify(client, auth).json()
    client.post(f"/api/v1/notifications/{n['id']}/archive")
    refired = notify(client, auth)
    assert refired.status_code == 201           # a new entry — archive is terminal
    assert refired.json()["id"] != n["id"]
    assert refired.json()["occurrences"] == 1


# --- idempotency ---------------------------------------------------------------


def test_idempotent_replay_is_suppressed(client, auth):
    a = notify(client, auth, idempotency_key="run-42")
    b = notify(client, auth, idempotency_key="run-42")
    assert a.status_code == 201
    assert b.status_code == 200
    assert b.json()["occurrences"] == 1          # replay did NOT count again


def test_distinct_keys_still_group(client, auth):
    notify(client, auth, idempotency_key="run-1")
    r = notify(client, auth, idempotency_key="run-2")
    assert r.json()["occurrences"] == 2


def test_idempotency_scoped_per_agent(client, auth):
    other_token = client.post("/api/v1/agents", json={"name": "roger"}).json()["token"]
    other = {"Authorization": f"Bearer {other_token}"}
    notify(client, auth, idempotency_key="shared-key")
    r = notify(client, other, idempotency_key="shared-key")
    assert r.status_code == 201                  # same key, different agent → new


# --- link hygiene ------------------------------------------------------------------
#
# Actions and source links render as click-outs in the UI, and the senders are
# LLMs acting on untrusted content — a javascript: URL must die at the door.


def test_non_web_action_url_rejected(client, auth):
    for url in ("javascript:alert(1)", "data:text/html,hi", "file:///etc/passwd",
                "/relative/path", "linear.app/no-scheme"):
        r = notify(client, auth, actions=[{"label": "Open", "url": url}])
        assert r.status_code == 422, url


def test_non_web_source_link_rejected(client, auth):
    r = notify(client, auth, source={"app": "linear", "link": "javascript:alert(1)"})
    assert r.status_code == 422


def test_web_urls_accepted(client, auth):
    r = notify(client, auth,
               source={"app": "linear", "link": "https://linear.app/acme/issue/PROJ-1"},
               actions=[{"label": "Open", "url": "http://127.0.0.1:8765/x"}])
    assert r.status_code == 201


# --- category is the only route -------------------------------------------------
#
# On MCP the tool name carries the split, so an agent dropping to the wire format
# reasonably assumes `type: "request_input"` does the same. It does not: `category`
# routes and defaults to activity, so a blocking ask lands in the wrong feed with
# nothing on it to show what it was meant to be.


def test_tool_name_in_type_is_rejected(client, auth):
    for bad in ("request_input", "report_activity"):
        r = notify(client, auth, type=bad, category="activity")
        assert r.status_code == 422, bad
        # The error has to name the field the agent actually wanted.
        assert "category" in r.text


def test_the_rejection_names_a_usable_replacement(client, auth):
    r = notify(client, auth, type="request_input")
    assert "input.needed" in r.text


def test_event_names_that_merely_contain_a_tool_name_are_fine(client, auth):
    for ok in ("input.needed", "request_input.sent", "agent.request_input"):
        assert notify(client, auth, type=ok, group_key=ok).status_code == 201


def test_category_still_defaults_to_activity(client, auth):
    """Omitted, not null — the default is what makes the mis-file silent."""
    r = client.post("/api/v1/notifications", headers=auth,
                    json={"type": "job.finished", "title": "Nightly reconcile passed"})
    assert r.status_code == 201
    assert r.json()["category"] == "activity"


def test_high_priority_does_not_imply_attention(client, auth):
    """The two axes are independent — the whole point of the split."""
    r = notify(client, auth, type="job.failed", category="activity", priority="high")
    assert r.json()["category"] == "activity"
    assert r.json()["priority"] == "high"
