"""Database engine, session factory, declarative Base and the FastAPI `get_db`
dependency.

SQLAlchemy 2.0 style. The engine is created once from the settings DB URL; each
request gets its own short-lived session that is always closed afterwards.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_pre_ping=True,  # transparently recover dropped connections
    echo=_settings.debug,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    """Declarative base all ORM models inherit from (defined in Phase 1)."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a session, guarantee it is closed.

    Usage:
        @router.get("/x")
        def handler(db: Session = Depends(get_db)):
            ...
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
