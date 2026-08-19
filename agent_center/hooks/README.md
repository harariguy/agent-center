# Per-harness session hooks

One directory per harness. Each holds the file(s) an agent writes into its own
harness so the notify policy is *delivered* at the start of every session,
instead of depending on the harness's skill scan to surface the skill.

Served at `GET /api/v1/hooks/<harness>/<file>` (loaders in `../docs.py`, routes
in `../main.py`), with the literal `{base}` replaced by the requesting server's
base URL — the same mechanism as `skill.md`, for the same reason: the installed
copy must carry the address that worked for the agent that fetched it.

Design rules every harness hook follows:

- **Injection only.** The hook puts the policy in front of the model; it never
  sends notifications itself. Every card stays model-authored.
- **Quiet.** First message of a session, once. No per-turn nudges, no blocking.
- **Fail open.** A broken hook must never break a run.
- **Kill switch.** `AGENT_CENTER_ENFORCE=off` disables it without uninstalling.
- **Exactly one `{base}` literal** in the source (the `DEFAULT_BASE` assignment)
  — serving does a blind string replace.

## hermes/

`plugin.py` is installed as `~/.hermes/plugins/agent-center/__init__.py` with
`plugin.yaml` beside it, then opted in with `hermes plugins enable agent-center`
(Hermes standalone plugins are allowlisted, and unlike shell hooks, plugin hooks
need no TTY consent — so gateway and cron runs are covered). It registers a
single `pre_llm_call` hook; Hermes prepends the returned `context` to the user
message on the first turn only (`is_first_turn`, with a per-session fallback for
older payloads).

Verify: `hermes plugins list` shows it enabled, and the first message of a fresh
session can be asked to quote the injected `[agent-center]` block back. Note
`hermes hooks list`/`test` covers shell hooks only — the plugin correctly does
not appear there.

## Adding a harness

Mirror the layout: `hooks/<harness>/` with the installable artifact(s), a
read-once template + `{base}` renderer in `../docs.py`, a route in `../main.py`,
an install step (and single-prompt extra) in `frontend/src/lib/install.ts`, and
served-content + behavior tests in `tests/test_hooks.py`.
