"""SQLAlchemy 2.0 models — the four tables from the design.

Portability notes (SQLite by default, Postgres via DATABASE_URL):
- Primary keys are uuid4 hex strings: portable, no autoincrement coupling, safe
  to generate client-side.
- All timestamps are timezone-aware UTC. `DateTime(timezone=True)` preserves the
  offset on Postgres; SQLite stores the ISO string as-is, so `utcnow()` is the
  only correct way to produce values here.
- JSON columns use SQLAlchemy's `JSON`, which maps to JSON1 on SQLite and
  jsonb-compatible json on Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agent"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    # sha256 of the bearer token. Tokens are 256-bit random values, so a fast
    # hash is the right choice (bcrypt/argon2 exist to slow down *guessable*
    # secrets; these are not guessable).
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notifications: Mapped[list[Notification]] = relationship(back_populates="agent")


class ViewerToken(Base):
    """A read/triage credential for human-facing clients (menu bar, scripts).

    Deliberately not a role on Agent: agents are senders — they appear in the
    UI with slugs, icons, and facet counts. A viewer token is a device
    credential; it must never show up as a sender. Same 256-bit-random +
    sha256 scheme as agent tokens, distinct `anv_` prefix so a token's role
    is legible in env files and logs.
    """

    __tablename__ = "viewer_token"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    label: Mapped[str] = mapped_column(String(120), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = (
        # The grouping lookup: open notification for (agent, group_key).
        Index("ix_notification_agent_group", "agent_id", "group_key"),
        Index("ix_notification_agent_fingerprint", "agent_id", "fingerprint"),
        # The feed ordering.
        Index("ix_notification_last_seen", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent.id"))

    # Grouping: agent-supplied key when present, server fingerprint otherwise.
    group_key: Mapped[str | None] = mapped_column(String(200))
    fingerprint: Mapped[str] = mapped_column(String(40))

    category: Mapped[str] = mapped_column(String(16))          # activity | attention
    type: Mapped[str] = mapped_column(String(100))             # e.g. "pr.opened"
    priority: Mapped[str] = mapped_column(String(8), default="normal")

    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    source_app: Mapped[str | None] = mapped_column(String(60))
    source_link: Mapped[str | None] = mapped_column(String(2000))
    actions_json: Mapped[list | None] = mapped_column(JSON)     # [{label, url}] — link-only in v1
    tags_json: Mapped[list | None] = mapped_column(JSON)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)

    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Triage state. Regression semantics (see core/ingest.py): a new occurrence
    # clears read_at and snoozed_until. Archive is terminal for ingest grouping,
    # though a human may restore the entry when no newer copy is active.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent: Mapped[Agent] = relationship(back_populates="notifications")
    occurrence_rows: Mapped[list[Occurrence]] = relationship(
        back_populates="notification",
        cascade="all, delete-orphan",
        order_by="Occurrence.seen_at",
    )


class Occurrence(Base):
    """One fire of a notification — grouping folds repeats into these."""

    __tablename__ = "occurrence"
    __table_args__ = (
        # At-most-once ingest for retrying clients. agent_id is denormalised
        # here precisely so this constraint can exist.
        UniqueConstraint("agent_id", "idempotency_key", name="uq_occurrence_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    notification_id: Mapped[str] = mapped_column(ForeignKey("notification.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload_json: Mapped[dict | None] = mapped_column(JSON)

    notification: Mapped[Notification] = relationship(back_populates="occurrence_rows")


class Meta(Base):
    """Install-scoped key/value state. One row today: `session_secret`, the
    random key that signs session cookies (see auth.py). It lives in the
    database rather than on disk so serverless deploys — which share a
    database but no filesystem — agree on one secret across instances."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256))


class Rule(Base):
    """Mute/snooze rules. Schema ships in v1; evaluation arrives in M2."""

    __tablename__ = "rule"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(20))   # agent | source_app | type | tag
    value: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(20), default="mute")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
