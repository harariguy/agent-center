"""Runtime configuration — 12-factor, everything from the environment.

A single dataclass rather than pydantic-settings: four knobs don't justify a
dependency, and `Settings.from_env(**overrides)` gives tests a clean way to
construct configs without touching the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOME = Path.home() / ".agent-center"


@dataclass(frozen=True)
class Settings:
    database_url: str
    host: str = "127.0.0.1"
    port: int = 8765
    # Empty string disables UI auth — the localhost default. Set it (or put the
    # server behind a tunnel/reverse proxy) when hosting.
    admin_password: str = ""
    retention_days: int = 90

    # Ingest hardening (plan: "hardening from day one").
    max_body_bytes: int = 64 * 1024
    rate_limit_per_minute: int = 120

    # Escape hatch for the fail-closed exposure check in create_app — for
    # deployments already behind a tailnet or an authenticating reverse proxy.
    allow_insecure_bind: bool = False

    @classmethod
    def from_env(cls, **overrides) -> Settings:
        home = Path(os.environ.get("AGENT_CENTER_HOME", DEFAULT_HOME))
        values = {
            "database_url": os.environ.get(
                "DATABASE_URL", f"sqlite:///{home / 'notifications.db'}"
            ),
            "host": os.environ.get("HOST", "127.0.0.1"),
            "port": int(os.environ.get("PORT", "8765")),
            "admin_password": os.environ.get("ADMIN_PASSWORD", ""),
            "retention_days": int(os.environ.get("RETENTION_DAYS", "90")),
            "allow_insecure_bind": os.environ.get("ALLOW_INSECURE_BIND", "") == "1",
        }
        values.update(overrides)
        settings = cls(**values)
        # Ensure the default SQLite directory exists before the engine touches it.
        if settings.database_url.startswith("sqlite:///"):
            Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(
                parents=True, exist_ok=True
            )
        return settings
