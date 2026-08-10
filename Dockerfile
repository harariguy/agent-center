# Stage 1: build the web UI into agent_notifications/static/ (vite's outDir).
FROM node:22-alpine AS frontend
WORKDIR /build
ENV CI=true
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/
RUN cd frontend && pnpm install --frozen-lockfile
COPY frontend/ frontend/
# vite writes to ../agent_notifications/static — create the parent it expects.
RUN mkdir -p agent_notifications && cd frontend && pnpm build

# Stage 2: runtime. One process, one worker — SQLite and the in-process rate
# limiter both assume a single process. Scale the box, not the worker count.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY agent_notifications/ agent_notifications/
COPY --from=frontend /build/agent_notifications/static/ agent_notifications/static/
RUN pip install --no-cache-dir ".[postgres]"

# State lives here: SQLite database unless DATABASE_URL points elsewhere.
ENV AGENT_NOTIFICATIONS_HOME=/data
VOLUME /data

ENV HOST=0.0.0.0 PORT=8765
EXPOSE 8765

# ADMIN_PASSWORD is required at runtime: the server refuses to start on a
# public bind without it (ALLOW_INSECURE_BIND=1 opts out behind a tailnet
# or authenticating proxy).
CMD ["agent-notifications", "serve"]
