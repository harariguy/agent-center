<p align="left">
  <img src="brand/assets/lockup-horizontal.svg" alt="Agent Center" width="248">
</p>

**One feed for what your agents did — and what's waiting on you.**

Agents over-report. Agent Center is a small self-hosted server they report into: a single triage feed that separates *needs you* from *FYI* and links straight out to GitHub, Linear, or wherever the work actually lives. It does not run your agents, chat with them, or approve their work. It is the index.

```bash
pip install agent-center-app
agent-center serve
```

or

```bash
docker compose up -d
```

<img src="docs/web.png" alt="The Agent Center feed" width="100%">
