"""
Database session management. SQLAlchemy 2.x style.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=settings.debug,
    connect_args={
        "connect_timeout": settings.db_connect_timeout,
        "options": "-c timezone=UTC",
    },
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models."""


def check_db_connection() -> None:
    """
    Verify database connectivity. Raises if unreachable.
    Call during application startup.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
