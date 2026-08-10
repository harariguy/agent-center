# Contributing

Thanks for considering it. This is a small, deliberately-scoped project — the
notes below keep contributions painless on both sides.

## Scope first

Agent Center is a **notification layer only**: agents write, humans read
and click out. Replies, approvals, agent orchestration, or anything that makes
this a place where work *happens* rather than where it is *reported* is out of
scope — see "Deliberately not on the roadmap" in the README. PRs in that
direction will be declined kindly, so open an issue to discuss direction before
building anything large.

## Development setup

Backend (Python ≥ 3.11):

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                        # the whole suite runs in ~2s
.venv/bin/agent-center serve     # → http://127.0.0.1:8765
```

Frontend (Node 20+, pnpm):

```sh
cd frontend
pnpm install
pnpm dev          # dev server on :5173, proxies /api to :8765
pnpm lint
pnpm build        # emits into agent_center/static/
```

macOS client (optional; macOS 14+, Command Line Tools suffice):

```sh
cd clients/macos && make build
```

## Checks

CI runs `ruff check`, `pytest` (3.11–3.13), `pnpm lint`, `pnpm build`, and a
Swift build of the macOS client. Run the ones you touched before pushing:

```sh
.venv/bin/ruff check agent_center tests api
.venv/bin/pytest
cd frontend && pnpm lint && pnpm build
```

There is no enforced auto-formatter — match the style of the surrounding code.
The codebase leans on comments that explain *why*, not *what*; keep that up.

## Pull requests

- Small and focused beats large and sweeping.
- Behavior changes come with tests. The test suite is fast and honest — keep it
  that way.
- Anything touching auth, tokens, or the exposure checks gets extra scrutiny;
  say explicitly in the PR what the security reasoning is.
