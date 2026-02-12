"""
Pytest configuration and fixtures.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Load .env for tests (macOS often uses $USER, not "postgres")
_test_user = os.getenv("PGUSER") or os.getenv("USER") or "postgres"
_test_url = f"postgresql+psycopg://{_test_user}@localhost:5432/signalforge_test"
os.environ.setdefault("DATABASE_URL", _test_url)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("INTERNAL_JOB_TOKEN", "test-internal-token")


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    from app.main import app
    return TestClient(app)


@pytest.fixture(scope="session")
def _ensure_migrations() -> None:
    """Create test DB if needed and run migrations once per test session."""
    import subprocess
    import sys

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Create test database if it doesn't exist (CREATE DATABASE requires autocommit)
    _user = os.getenv("PGUSER") or os.getenv("USER") or "postgres"
    _create_db_url = f"postgresql+psycopg://{_user}@localhost:5432/postgres"
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(_create_db_url)
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("CREATE DATABASE signalforge_test"))
        engine.dispose()
    except Exception:
        pass  # DB may already exist

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, f"alembic upgrade head failed: {result.stderr}"


@pytest.fixture
def db(_ensure_migrations: None) -> Session:
    """Database session for model tests."""
    from app.db import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
