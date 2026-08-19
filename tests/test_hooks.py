"""The served Hermes hook: the artifact an agent installs, and its behavior.

Two halves. The served-content tests mirror the skill tests in test_mcp.py: the
endpoint is ungated, `{base}` resolves against the requesting host, and the file
is runnable Python. The behavior tests exercise the plugin's one job — inject
the policy on the first turn of a session, and only then.
"""

from __future__ import annotations

import py_compile
import tempfile

import pytest

from agent_center.hooks.hermes import plugin

# --- served content ---------------------------------------------------------


def test_hermes_plugin_is_served_as_runnable_python(client):
    r = client.get("/api/v1/hooks/hermes/plugin.py")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/x-python")
    assert "{base}" not in r.text
    assert "http://testserver" in r.text
    with tempfile.NamedTemporaryFile("w", suffix=".py") as f:
        f.write(r.text)
        f.flush()
        py_compile.compile(f.name, doraise=True)


def test_hermes_plugin_carries_the_policy_and_the_seam(client):
    body = client.get("/api/v1/hooks/hermes/plugin.py").text
    assert "pre_llm_call" in body            # the injection seam
    assert "report_activity" in body         # the policy names the tools
    assert "request_input" in body
    assert "group_key" in body
    assert "/api/v1/notifications" in body   # the HTTP fallback path


def test_hermes_manifest_is_served_and_declares_the_hook(client):
    r = client.get("/api/v1/hooks/hermes/plugin.yaml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/yaml")
    assert "name: agent-center" in r.text
    assert "pre_llm_call" in r.text


def test_served_policy_injects_against_the_requested_host(client):
    """The served copy, executed: its injection carries the resolved base URL."""
    body = client.get("/api/v1/hooks/hermes/plugin.py").text
    ns: dict = {}
    exec(compile(body, "plugin.py", "exec"), ns)
    result = ns["inject_policy"](session_id="s1", is_first_turn=True)
    assert "http://testserver" in result["context"]
    assert "http://testserver/api/v1/notifications" in result["context"]


# --- injection behavior -------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_plugin_state(monkeypatch):
    monkeypatch.delenv("AGENT_CENTER_ENFORCE", raising=False)
    plugin._seen_sessions.clear()


def test_injects_on_the_first_turn_only():
    first = plugin.inject_policy(session_id="s1", is_first_turn=True)
    assert "report_activity" in first["context"]
    assert plugin.inject_policy(session_id="s1", is_first_turn=False) is None


def test_a_new_session_injects_again():
    assert plugin.inject_policy(session_id="s1", is_first_turn=True) is not None
    assert plugin.inject_policy(session_id="s2", is_first_turn=True) is not None


def test_falls_back_to_session_tracking_when_is_first_turn_is_absent():
    """Older Hermes payloads have no is_first_turn kwarg."""
    assert plugin.inject_policy(session_id="s1") is not None
    assert plugin.inject_policy(session_id="s1") is None
    assert plugin.inject_policy(session_id="s2") is not None


def test_without_a_session_id_the_fallback_stays_silent():
    """No way to tell turns apart -> never inject rather than inject always."""
    assert plugin.inject_policy() is None


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("AGENT_CENTER_ENFORCE", "off")
    assert plugin.inject_policy(session_id="s1", is_first_turn=True) is None


def test_unknown_kwargs_are_tolerated():
    """Hermes' hook contract adds kwargs over time; the plugin must not care."""
    result = plugin.inject_policy(
        session_id="s1", is_first_turn=True,
        user_message="hi", conversation_history=[], model="m", platform="cli",
        telemetry_schema_version=2, turn_id="t1",
    )
    assert result is not None


def test_register_wires_pre_llm_call():
    calls = []

    class Ctx:
        def register_hook(self, event, fn):
            calls.append((event, fn))

    plugin.register(Ctx())
    assert calls == [("pre_llm_call", plugin.inject_policy)]
