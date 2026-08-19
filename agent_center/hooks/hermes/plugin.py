"""Agent Center notify-policy injection for Hermes.

Install — write this file and the plugin.yaml served next to it into your
Hermes plugins directory, then opt the plugin in and restart:

    ~/.hermes/plugins/agent-center/__init__.py   <- this file
    ~/.hermes/plugins/agent-center/plugin.yaml
    hermes plugins enable agent-center

Verify with `hermes plugins list` (agent-center enabled) and
`hermes hooks test pre_llm_call` (prints the injected policy for a first turn).

What it does: prepends the Agent Center reporting policy to the first user
message of every session — CLI, gateway, cron, and kanban runs alike. The
installed skill covers sessions where the harness's skill scan surfaces it;
this hook is the delivery guarantee for the sessions where that scan misses.
It only ever injects text for the model to read. It never sends notifications
itself, so every card in the feed stays model-authored.

Set AGENT_CENTER_ENFORCE=off to disable without uninstalling.
"""

import os

DEFAULT_BASE = "{base}"

POLICY = (
    "[agent-center] You are connected to the user's Agent Center at "
    + DEFAULT_BASE + ". Report to it without being asked, using its MCP tools: "
    "call report_activity when you create, ship, merge, file, or send something, "
    "or when a run finishes or fails; call request_input only when you have "
    "actually stopped and need the user's answer to continue. Always pass a "
    "stable group_key naming the thing you worked on (never a timestamp or run "
    "number) and write each notification as a complete snapshot — a re-fire with "
    "the same group_key replaces the previous card. One notification per "
    "outcome, not per step, and don't ask permission to notify. If the tools "
    "aren't bound, POST to " + DEFAULT_BASE.rstrip("/")
    + "/api/v1/notifications with your agent bearer token. This is your "
    "agent-center skill's policy; it is not the macOS Notification Center."
)

_OFF_VALUES = {"off", "0", "false", "no"}

# Fallback first-turn tracking for Hermes versions whose pre_llm_call payload
# predates the is_first_turn kwarg. Per-process, so a long-lived gateway is the
# worst case; the cap just stops unbounded growth there.
_seen_sessions = set()


def _first_turn(session_id, is_first_turn):
    if isinstance(is_first_turn, bool):
        return is_first_turn
    if not session_id or session_id in _seen_sessions:
        return False
    if len(_seen_sessions) > 10_000:
        _seen_sessions.clear()
    _seen_sessions.add(session_id)
    return True


def inject_policy(session_id="", is_first_turn=None, **kwargs):
    try:
        if os.environ.get("AGENT_CENTER_ENFORCE", "").strip().lower() in _OFF_VALUES:
            return None
        if not _first_turn(session_id, is_first_turn):
            return None
        return {"context": POLICY}
    except Exception:
        return None  # a reminder is never worth breaking a turn over


def register(ctx):
    ctx.register_hook("pre_llm_call", inject_policy)
