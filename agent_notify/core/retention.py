"""Retention: delete notifications not seen for RETENTION_DAYS.

Bulk deletes rather than ORM cascade: cascade would require loading every
doomed row into the session. Occurrences go first (they reference the
notification), then the notifications themselves.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import Notification, Occurrence, utcnow


def prune(db: Session, retention_days: int) -> int:
    """Delete notifications whose last_seen_at is older than the cutoff.

    Returns the number of notifications deleted. `retention_days <= 0`
    disables retention entirely.
    """
    if retention_days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=retention_days)
    doomed = db.scalars(
        select(Notification.id).where(Notification.last_seen_at < cutoff)
    ).all()
    if not doomed:
        return 0
    db.execute(delete(Occurrence).where(Occurrence.notification_id.in_(doomed)))
    db.execute(delete(Notification).where(Notification.id.in_(doomed)))
    db.commit()
    return len(doomed)
