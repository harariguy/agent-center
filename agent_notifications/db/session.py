"""Engine + session factory, built per-app from Settings.

No module-level engine: the app factory owns one, which keeps tests hermetic
(each test builds its own in-memory database) and makes DATABASE_URL a plain
constructor argument instead of ambient state.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base


def make_engine(database_url: str):
    kwargs: dict = {}
    if database_url.startswith("sqlite"):
        # FastAPI handles requests across threads; SQLite objects to that by
        # default. StaticPool keeps ":memory:" databases alive across
        # connections (essential for tests; harmless for file databases).
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url or database_url in ("sqlite://", "sqlite:///"):
            kwargs["poolclass"] = StaticPool
    else:
        # Server databases: validate pooled connections before use. Serverless
        # hosts freeze instances mid-pool and Postgres closes idle sessions;
        # pre-ping turns both into a reconnect instead of a 500.
        kwargs["pool_pre_ping"] = True
    engine = create_engine(database_url, **kwargs)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # pragma: no cover - trivial
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine) -> None:
    """Create the schema. Alembic arrives with the first real schema change."""
    Base.metadata.create_all(engine)
