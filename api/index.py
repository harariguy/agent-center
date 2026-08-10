"""Vercel entrypoint (repo-root /api is Vercel's convention; unrelated to the
agent_notifications.api package).

Module-level construction is deliberate here and only here: Vercel imports
this at cold start, which is exactly when the app should be built. Everywhere
else imports stay side-effect free (see agent_notifications/main.py).

Deployment contract:
- DATABASE_URL must point at Postgres (Neon's pooled connection string) —
  serverless has no persistent disk for SQLite.
- ADMIN_PASSWORD must be set; create_app refuses to start without it when
  the VERCEL env marker is present.
- CRON_SECRET should hold a viewer token so the daily cron in vercel.json
  passes the viewer gate on /api/v1/prune.
"""

from agent_notifications.main import create_app

app = create_app()
