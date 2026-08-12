"""Pydantic request/response models — the public API contract."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["activity", "attention"]
Priority = Literal["min", "low", "normal", "high", "urgent"]

# Namespaced event names: "pr.opened", "job.failed", "input.needed".
TYPE_PATTERN = r"^[a-z0-9_]+(\.[a-z0-9_]+)*$"

# The MCP write tools, which are also the two names an agent reaching for the
# wire format is most likely to put in `type`.
RESERVED_TYPES = {"report_activity", "request_input"}


def validate_event_type(value: str) -> str:
    """Reject a tool name sitting in the `type` field.

    On the MCP surface the tool *is* the category, so an agent that drops down
    to `POST /notifications` reasonably assumes `type: "request_input"` routes
    the same way. It does not — `category` routes, `type` only labels — so the
    ask lands in Activity with nothing to show it was meant to block. The two
    fields never disagree loudly enough to notice, so the contradiction dies at
    the door instead: this is the one mistake the split cannot survive.
    """
    if value in RESERVED_TYPES:
        raise ValueError(
            f"'{value}' is a tool name, not an event type. `type` labels what "
            "happened (input.needed, pr.opened, job.failed); `category` chooses "
            "the feed — 'attention' if you have stopped and need the human, "
            "'activity' otherwise."
        )
    return value


def require_web_url(value: str) -> str:
    """Only absolute http(s) URLs may enter the system as links.

    Links and actions render as click-outs in the UI, so a `javascript:` or
    `data:` URL from a compromised or prompt-injected agent would be script
    execution one click away. Allowlisting at the door beats blocklisting at
    every renderer.
    """
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("must be an absolute http:// or https:// URL")
    return value


class Source(BaseModel):
    app: str = Field(max_length=60)
    link: str | None = Field(default=None, max_length=2000)

    @field_validator("link")
    @classmethod
    def _link_is_web(cls, v: str | None) -> str | None:
        return None if v is None else require_web_url(v)


class Action(BaseModel):
    """Link-only in v1 — no callbacks, no verdicts."""

    label: str = Field(max_length=60)
    url: str = Field(max_length=2000)


class ActionIn(Action):
    """Ingest-side Action: the URL scheme is enforced at the door only — a bad
    row already in the database must not be able to break reads of the feed."""

    @field_validator("url")
    @classmethod
    def _url_is_web(cls, v: str) -> str:
        return require_web_url(v)


class NotificationIn(BaseModel):
    type: str = Field(
        pattern=TYPE_PATTERN, max_length=100,
        description="Namespaced event name, lowercase dotted: pr.opened, job.failed, "
                    "input.needed. Labels what happened; it does NOT route — see "
                    "`category` for that.",
    )
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=4000)
    category: Category = Field(
        default="activity",
        description="Which feed this lands in. 'attention' means you have stopped and "
                    "cannot continue without the human; 'activity' is everything else. "
                    "This is the only field that decides it.",
    )
    priority: Priority = Field(
        default="normal",
        description="How loud, independent of `category`. A high-priority activity item "
                    "is normal — urgency and blocking are different questions.",
    )
    group_key: str | None = Field(default=None, max_length=200)
    source: Source | None = None
    actions: list[ActionIn] = Field(default_factory=list, max_length=5)
    tags: list[str] = Field(default_factory=list, max_length=10)
    metadata: dict = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _type_is_not_a_route(cls, v: str) -> str:
        return validate_event_type(v)


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    agent_name: str
    group_key: str | None
    category: Category
    type: str
    priority: Priority
    title: str
    body: str
    source_app: str | None
    source_link: str | None
    actions: list[Action]
    tags: list[str]
    occurrences: int
    first_seen_at: datetime
    last_seen_at: datetime
    read_at: datetime | None
    snoozed_until: datetime | None
    archived_at: datetime | None


class OccurrenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seen_at: datetime
    payload_json: dict | None


class NotificationDetail(NotificationOut):
    metadata: dict
    history: list[OccurrenceOut]


class SnoozeIn(BaseModel):
    until: datetime


class FeedPage(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None


class FacetValue(BaseModel):
    """One filterable value, with how many notifications carry it."""

    value: str
    label: str | None = None  # display name where it differs from the value (agents)
    count: int


class FeedCounts(BaseModel):
    total: int
    unread: int
    attention: int
    attention_unread: int
    activity: int
    activity_unread: int


class Facets(BaseModel):
    """What the feed can be filtered by, so the UI never offers a dead filter."""

    agents: list[FacetValue]
    types: list[FacetValue]
    priorities: list[FacetValue]
    source_apps: list[FacetValue]
    tags: list[FacetValue]
    counts: FeedCounts


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    created_at: datetime
    last_seen_at: datetime | None


class AgentCreated(AgentOut):
    # Returned exactly once, at creation. Only the hash is stored.
    token: str


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
