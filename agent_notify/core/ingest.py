"""Ingest: validate → dedupe → group → persist.

The one write path in the system. Three layered behaviours, in order:

1. **Idempotency** — a retried delivery (same `Idempotency-Key`) must not count
   twice. Distinct from grouping: idempotency suppresses a duplicate *delivery*,
   grouping folds *genuine repeats*.
2. **Grouping** — a fire that matches an open notification's (agent, group_key)
   — or fingerprint, when the agent supplied no key — becomes an occurrence of
   that notification, not a new row.
3. **Regression semantics** (Sentry's model) — what keeps triage honest when a
   grouped item fires again:
     · read     → unread again (`read_at` cleared)
     · snoozed  → wakes (snooze means "quiet unless something changes")
     · archived → a NEW notification opens; archive is terminal for that entry.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.models import Agent, Notification, Occurrence, utcnow
from ..schemas import NotificationIn
from .grouping import fingerprint


@dataclass
class IngestResult:
    notification: Notification
    created: bool        # new notification row (HTTP 201) vs grouped/duplicate (200)
    deduplicated: bool   # suppressed by Idempotency-Key


def _find_open(db: Session, agent_id: str, group_key: str | None, fp: str) -> Notification | None:
    """The open (non-archived) notification this fire belongs to, if any.

    Agent-supplied group_key wins; the fingerprint only stands in when the agent
    sent no key. Keys and fingerprints are deliberately NOT cross-matched — an
    explicit key is a statement of identity, a fingerprint is a guess.
    """
    q = select(Notification).where(
        Notification.agent_id == agent_id,
        Notification.archived_at.is_(None),
    )
    if group_key is not None:
        q = q.where(Notification.group_key == group_key)
    else:
        q = q.where(Notification.group_key.is_(None), Notification.fingerprint == fp)
    return db.scalars(q.order_by(Notification.last_seen_at.desc())).first()


def ingest(
    db: Session,
    agent: Agent,
    data: NotificationIn,
    idempotency_key: str | None = None,
) -> IngestResult:
    # 1. Idempotency — replay of a delivery we already recorded.
    if idempotency_key:
        seen = db.scalar(
            select(Occurrence).where(
                Occurrence.agent_id == agent.id,
                Occurrence.idempotency_key == idempotency_key,
            )
        )
        if seen:
            return IngestResult(seen.notification, created=False, deduplicated=True)

    now = utcnow()
    fp = fingerprint(data.title)
    payload = data.model_dump(mode="json")

    existing = _find_open(db, agent.id, data.group_key, fp)

    if existing is not None:
        # 2. Group: fold into the open notification.
        existing.occurrences += 1
        existing.last_seen_at = now
        # The latest fire is the freshest description of the item.
        existing.title = data.title
        existing.body = data.body
        existing.priority = data.priority
        existing.category = data.category
        if data.source:
            existing.source_app = data.source.app
            existing.source_link = data.source.link
        if data.actions:
            existing.actions_json = [a.model_dump() for a in data.actions]
        # 3. Regression: re-firing is news — surface it again.
        existing.read_at = None
        existing.snoozed_until = None
        notification = existing
        created = False
    else:
        notification = Notification(
            agent_id=agent.id,
            group_key=data.group_key,
            fingerprint=fp,
            category=data.category,
            type=data.type,
            priority=data.priority,
            title=data.title,
            body=data.body,
            source_app=data.source.app if data.source else None,
            source_link=data.source.link if data.source else None,
            actions_json=[a.model_dump() for a in data.actions],
            tags_json=data.tags,
            metadata_json=data.metadata,
            occurrences=1,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(notification)
        created = True

    notification.occurrence_rows.append(
        Occurrence(
            agent_id=agent.id,
            idempotency_key=idempotency_key,
            seen_at=now,
            payload_json=payload,
        )
    )

    try:
        db.commit()
    except IntegrityError:
        # Concurrent retry raced us on uq_occurrence_idempotency: the other
        # request won; report its result as a dedupe rather than failing.
        db.rollback()
        seen = db.scalar(
            select(Occurrence).where(
                Occurrence.agent_id == agent.id,
                Occurrence.idempotency_key == idempotency_key,
            )
        )
        if seen:
            return IngestResult(seen.notification, created=False, deduplicated=True)
        raise

    return IngestResult(notification, created=created, deduplicated=False)
