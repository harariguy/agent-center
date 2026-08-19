"""The documents this server hands to agents, from one copy each.

- `guide.md` — the field rules. Served as the MCP `initialize` instructions and at
  `GET /api/v1/guide.md`.
- `skill.md` — a SKILL.md an agent writes into its own harness so it notifies
  *unprompted*. Served at `GET /api/v1/skill.md`.
- `hooks/<harness>/…` — per-harness lifecycle hooks an agent installs into its
  harness so the policy is *delivered* every session. Served at
  `GET /api/v1/hooks/<harness>/<file>`.

The split matters. MCP delivers the capability: once connected, an agent *can*
notify. It does not deliver the policy, so an agent only notifies when asked —
harnesses decide what to do by scanning a skill index before they act, and a
server that exists only as an `mcp_servers` entry is invisible to that pass. The
skill is what makes reporting a habit rather than a request — but the skill is
still subject to that scan. A harness hook closes the last gap by injecting the
policy in front of the first message of every session: guaranteed delivery,
while every notification stays model-authored.

Skill triggers are therefore written as post-conditions on the agent's own work
("you shipped something", "you stopped and need a decision") rather than as user
requests ("the user asks to notify"). Phrased the second way — the way most skills
are — the skill only ever fires when the user already thought to ask, which is
exactly the failure it exists to prevent.
"""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).parent

GUIDE_PATH = _HERE / "guide.md"
SKILL_PATH = _HERE / "skill.md"
HOOKS_DIR = _HERE / "hooks"

# Read once at import: a few kilobytes each, never changing at runtime.
GUIDE = GUIDE_PATH.read_text(encoding="utf-8")
_SKILL_TEMPLATE = SKILL_PATH.read_text(encoding="utf-8")
_HERMES_PLUGIN_TEMPLATE = (HOOKS_DIR / "hermes" / "plugin.py").read_text(encoding="utf-8")
HERMES_PLUGIN_YAML = (HOOKS_DIR / "hermes" / "plugin.yaml").read_text(encoding="utf-8")


def skill(base_url: str) -> str:
    """The skill with `{base}` resolved, so its urls are ready to fetch.

    Rendered per request rather than baked in: the reachable address depends on
    how the server is being reached — localhost, a LAN ip, or a tunnel — and an
    agent copying a skill file needs the url that worked for *it*.
    """
    return _SKILL_TEMPLATE.replace("{base}", base_url.rstrip("/"))


def hermes_plugin(base_url: str) -> str:
    """The Hermes plugin with `{base}` resolved, ready to write and run.

    Same per-request rendering as `skill()`, for the same reason: the plugin
    bakes in the server address that worked for the agent installing it.
    """
    return _HERMES_PLUGIN_TEMPLATE.replace("{base}", base_url.rstrip("/"))
