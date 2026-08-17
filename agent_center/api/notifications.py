"""Notification routes: ingest (agents) and the feed (humans)."""

from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import Text, case, cast, func, or_, select
from sqlalchemy.orm import Session

from ..auth import get_db, require_agent, require_viewer
from ..core.ingest import ingest
from ..db.models import Agent, Notification, utcnow
from ..errors import problem
from ..schemas import (
    Facets,
    FacetValue,
    FeedCounts,
    FeedPage,
    NotificationDetail,
    NotificationIn,
    NotificationOut,
    SnoozeIn,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def to_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        agent_id=n.agent_id,
        agent_name=n.agent.name,
        group_key=n.group_key,
        category=n.category,
        type=n.type,
        priority=n.priority,
        title=n.title,
        body=n.body,
        source_app=n.source_app,
        source_link=n.source_link,
        actions=n.actions_json or [],
        tags=n.tags_json or [],
        occurrences=n.occurrences,
        first_seen_at=n.first_seen_at,
        last_seen_at=n.last_seen_at,
        read_at=n.read_at,
        snoozed_until=n.snoozed_until,
        archived_at=n.archived_at,
    )


# --- ingest (agent-authenticated) --------------------------------------------


@router.post("", response_model=NotificationOut)
def create_notification(
    data: NotificationIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    agent: Agent = Depends(require_agent),
):
    if not request.app.state.rate_limiter.allow(agent.id):
        raise problem(429, "Rate limited",
                      "This agent is sending notifications too fast; slow down and retry.")

    idempotency_key = request.headers.get("idempotency-key")
    if idempotency_key and len(idempotency_key) > 200:
        # Same cap the MCP facade declares — and the column is String(200),
        # which SQLite shrugs at but Postgres enforces with a DataError.
        raise problem(422, "Idempotency-Key too long",
                      "Idempotency keys are limited to 200 characters.")
    result = ingest(db, agent, data, idempotency_key=idempotency_key)
    # 201 for a new notification, 200 when the fire grouped into (or replayed
    # onto) an existing one — the body always carries the current state.
    response.status_code = 201 if result.created else 200
    return to_out(result.notification)


# --- feed (viewer-authenticated) ---------------------------------------------


PRIORITY_RANK = {"min": 1, "low": 2, "normal": 3, "high": 4, "urgent": 5}


def _encode_cursor(ts: datetime, nid: str, priority_rank: int | None = None) -> str:
    prefix = f"p:{priority_rank}|" if priority_rank is not None else ""
    raw = f"{prefix}{ts.isoformat()}|{nid}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str, int | None]:
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + pad).decode()
        priority_rank = None
        if raw.startswith("p:"):
            rank_raw, _, raw = raw.partition("|")
            priority_rank = int(rank_raw.removeprefix("p:"))
        ts_raw, separator, nid = raw.partition("|")
        if not separator or not nid:
            raise ValueError
        return datetime.fromisoformat(ts_raw), nid, priority_rank
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise problem(400, "Bad cursor",
                      "The cursor is not one this server issued.") from None


def _apply_feed_filters(
    stmt,
    *,
    category: str | None = None,
    type: str | None = None,
    agent: str | None = None,
    source_app: str | None = None,
    tag: str | None = None,
    priority: str | None = None,
    unread: bool | None = None,
    archived: bool = False,
    q: str | None = None,
):
    if archived:
        stmt = stmt.where(Notification.archived_at.is_not(None))
    else:
        now = utcnow()
        stmt = stmt.where(
            Notification.archived_at.is_(None),
            or_(Notification.snoozed_until.is_(None), Notification.snoozed_until <= now),
        )
    if category:
        stmt = stmt.where(Notification.category == category)
    if type:
        stmt = stmt.where(Notification.type == type)
    if agent:
        stmt = stmt.where(Agent.slug == agent)
    if source_app:
        stmt = stmt.where(Notification.source_app == source_app)
    if priority:
        stmt = stmt.where(Notification.priority == priority)
    if unread is True:
        stmt = stmt.where(Notification.read_at.is_(None))
    elif unread is False:
        stmt = stmt.where(Notification.read_at.is_not(None))
    if tag:
        stmt = stmt.where(
            func.lower(cast(Notification.tags_json, Text)).like(f'%"{tag.lower()}"%')
        )
    if q:
        needle = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Notification.title).like(needle)
            | func.lower(Notification.body).like(needle)
            | func.lower(func.coalesce(Notification.group_key, "")).like(needle)
        )
    return stmt


@router.get("", response_model=FeedPage, dependencies=[Depends(require_viewer)])
def list_notifications(
    db: Session = Depends(get_db),
    category: str | None = Query(default=None, pattern="^(activity|attention)$"),
    type: str | None = None,
    agent: str | None = Query(default=None, description="agent slug"),
    source_app: str | None = None,
    tag: str | None = None,
    priority: str | None = Query(default=None, pattern="^(min|low|normal|high|urgent)$"),
    unread: bool | None = None,
    archived: bool = False,
    q: str | None = Query(default=None, max_length=200),
    order: Literal["recent", "priority"] = "recent",
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
):
    stmt = _apply_feed_filters(
        select(Notification).join(Agent),
        category=category,
        type=type,
        agent=agent,
        source_app=source_app,
        tag=tag,
        priority=priority,
        unread=unread,
        archived=archived,
        q=q,
    )
    priority_rank = case(PRIORITY_RANK, value=Notification.priority, else_=0)

    if cursor:
        ts, nid, cursor_rank = _decode_cursor(cursor)
        if order == "priority":
            if cursor_rank is None:
                raise problem(400, "Bad cursor", "This cursor belongs to a different order.")
            stmt = stmt.where(
                (priority_rank < cursor_rank)
                | (
                    (priority_rank == cursor_rank)
                    & (
                        (Notification.last_seen_at < ts)
                        | ((Notification.last_seen_at == ts) & (Notification.id < nid))
                    )
                )
            )
        else:
            if cursor_rank is not None:
                raise problem(400, "Bad cursor", "This cursor belongs to a different order.")
            stmt = stmt.where(
                (Notification.last_seen_at < ts)
                | ((Notification.last_seen_at == ts) & (Notification.id < nid))
            )

    # id tiebreak keeps cursors stable when several rows share a timestamp.
    if order == "priority":
        stmt = stmt.order_by(
            priority_rank.desc(), Notification.last_seen_at.desc(), Notification.id.desc()
        )
    else:
        stmt = stmt.order_by(Notification.last_seen_at.desc(), Notification.id.desc())
    rows = db.scalars(stmt.limit(limit + 1)).all()

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        rank = PRIORITY_RANK.get(last.priority, 0) if order == "priority" else None
        next_cursor = _encode_cursor(last.last_seen_at, last.id, rank)

    return FeedPage(items=[to_out(n) for n in rows], next_cursor=next_cursor)


# Declared before /{notification_id} so "facets" isn't read as an id.
@router.get("/facets", response_model=Facets, dependencies=[Depends(require_viewer)])
def facets(request: Request, response: Response,
           db: Session = Depends(get_db), archived: bool = False):
    """Distinct filterable values over the current archive scope.

    Deliberately not narrowed by the caller's other filters: the menus should
    keep offering every value that exists, so picking one can't strand the user
    in a view whose own filter has vanished from the list.

    Sends an ETag so the UI's 30-second poll costs a 304 instead of a payload
    when nothing changed.
    """
    if archived:
        scope = Notification.archived_at.is_not(None)
    else:
        scope = (
            Notification.archived_at.is_(None)
            & or_(
                Notification.snoozed_until.is_(None),
                Notification.snoozed_until <= utcnow(),
            )
        )
    n = func.count(Notification.id)

    def grouped(col) -> list[FacetValue]:
        rows = db.execute(
            select(col, n).where(scope, col.is_not(None))
            .group_by(col).order_by(n.desc(), col)
        ).all()
        return [FacetValue(value=str(v), count=int(c)) for v, c in rows]

    agent_rows = db.execute(
        select(Agent.slug, Agent.name, n)
        .join(Notification, Notification.agent_id == Agent.id)
        .where(scope).group_by(Agent.slug, Agent.name).order_by(n.desc(), Agent.name)
    ).all()

    # Tags are a JSON list per row; counting them portably means folding in
    # Python rather than reaching for a backend-specific JSON operator.
    tag_counts: dict[str, int] = {}
    for (tags,) in db.execute(select(Notification.tags_json).where(scope)):
        for tag in tags or []:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    def count(*conditions) -> int:
        return db.scalar(select(n).where(scope, *conditions)) or 0

    unread = Notification.read_at.is_(None)
    attention = Notification.category == "attention"
    activity = Notification.category == "activity"

    result = Facets(
        agents=[FacetValue(value=slug, label=name, count=int(c))
                for slug, name, c in agent_rows],
        types=grouped(Notification.type),
        priorities=grouped(Notification.priority),
        source_apps=grouped(Notification.source_app),
        tags=[FacetValue(value=t, count=c)
              for t, c in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))],
        counts=FeedCounts(
            total=count(),
            unread=count(unread),
            attention=count(attention),
            attention_unread=count(attention, unread),
            activity=count(activity),
            activity_unread=count(activity, unread),
        ),
    )

    # Counts alone do not move when an already-unread grouped item fires again.
    # Include the newest occurrence timestamp so conditional clients still see
    # that feed change and can raise another banner.
    latest_seen_at = db.scalar(
        select(func.max(Notification.last_seen_at)).where(scope)
    )
    revision = latest_seen_at.isoformat() if latest_seen_at is not None else ""
    etag_payload = f"{result.model_dump_json()}|{revision}".encode()
    etag = 'W/"' + hashlib.sha256(etag_payload).hexdigest()[:32] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return result


@router.get("/{notification_id}", response_model=NotificationDetail,
            dependencies=[Depends(require_viewer)])
def get_notification(notification_id: str, db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None:
        raise problem(404, "Not found", "No notification with this id.")
    base = to_out(n)
    return NotificationDetail(
        **base.model_dump(),
        metadata=n.metadata_json or {},
        history=list(n.occurrence_rows),
    )


def _get_or_404(db: Session, notification_id: str) -> Notification:
    n = db.get(Notification, notification_id)
    if n is None:
        raise problem(404, "Not found", "No notification with this id.")
    return n


@router.post("/read-all", dependencies=[Depends(require_viewer)], status_code=204)
def read_all(
    db: Session = Depends(get_db),
    category: str | None = Query(default=None, pattern="^(activity|attention)$"),
    type: str | None = None,
    agent: str | None = Query(default=None, description="agent slug"),
    source_app: str | None = None,
    tag: str | None = None,
    priority: str | None = Query(default=None, pattern="^(min|low|normal|high|urgent)$"),
    q: str | None = Query(default=None, max_length=200),
):
    now = utcnow()
    stmt = _apply_feed_filters(
        select(Notification).join(Agent),
        category=category,
        type=type,
        agent=agent,
        source_app=source_app,
        tag=tag,
        priority=priority,
        unread=True,
        q=q,
    )
    for n in db.scalars(stmt):
        n.read_at = now
    db.commit()
    return Response(status_code=204)


@router.post("/{notification_id}/read", response_model=NotificationOut,
             dependencies=[Depends(require_viewer)])
def mark_read(notification_id: str, db: Session = Depends(get_db)):
    n = _get_or_404(db, notification_id)
    n.read_at = utcnow()
    db.commit()
    return to_out(n)


@router.post("/{notification_id}/unread", response_model=NotificationOut,
             dependencies=[Depends(require_viewer)])
def mark_unread(notification_id: str, db: Session = Depends(get_db)):
    n = _get_or_404(db, notification_id)
    n.read_at = None
    db.commit()
    return to_out(n)


@router.post("/{notification_id}/archive", response_model=NotificationOut,
             dependencies=[Depends(require_viewer)])
def archive(notification_id: str, db: Session = Depends(get_db)):
    """Terminal for this entry: a later re-fire opens a NEW notification."""
    n = _get_or_404(db, notification_id)
    n.archived_at = utcnow()
    n.snoozed_until = None
    if n.read_at is None:
        n.read_at = n.archived_at
    db.commit()
    return to_out(n)


@router.post("/{notification_id}/unarchive", response_model=NotificationOut,
             dependencies=[Depends(require_viewer)])
def unarchive(notification_id: str, db: Session = Depends(get_db)):
    n = _get_or_404(db, notification_id)
    if n.archived_at is None:
        return to_out(n)

    identity = (
        Notification.group_key == n.group_key
        if n.group_key is not None
        else (
            Notification.group_key.is_(None)
            & (Notification.fingerprint == n.fingerprint)
        )
    )
    conflict = db.scalar(
        select(Notification.id).where(
            Notification.id != n.id,
            Notification.agent_id == n.agent_id,
            Notification.archived_at.is_(None),
            identity,
        )
    )
    if conflict:
        raise problem(
            409,
            "Already active",
            "A newer notification for this item is already in the feed.",
        )
    n.archived_at = None
    db.commit()
    return to_out(n)


@router.post("/{notification_id}/snooze", response_model=NotificationOut,
             dependencies=[Depends(require_viewer)])
def snooze(notification_id: str, data: SnoozeIn, db: Session = Depends(get_db)):
    n = _get_or_404(db, notification_id)
    if n.archived_at is not None:
        raise problem(409, "Already archived", "Restore this notification before snoozing it.")
    until = data.until
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    else:
        until = until.astimezone(UTC)
    if until <= utcnow():
        raise problem(400, "Invalid snooze time", "Choose a time in the future.")
    n.snoozed_until = until
    db.commit()
    return to_out(n)
