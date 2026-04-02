from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import AppSettings
from app.domain.constants import DEFAULT_SQLITE_BUSY_TIMEOUT_MS
from app.persistence.base import Base


def create_sqlalchemy_engine(settings: AppSettings) -> Engine:
    engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute(f"PRAGMA busy_timeout = {DEFAULT_SQLITE_BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all_dev_only(engine: Engine) -> None:
    """Optional local helper for development only. Alembic is the canonical schema path."""
    Base.metadata.create_all(bind=engine)
