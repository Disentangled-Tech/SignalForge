"""
Pytest configuration and fixtures.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_constants import TEST_INTERNAL_JOB_TOKEN, TEST_SECRET_KEY

# Force test DB when pytest runs; don't inherit from .env (avoids polluting signalforge_dev)
_test_user = os.getenv("PGUSER") or os.getenv("USER") or "postgres"
_test_url = f"postgresql+psycopg://{_test_user}@localhost:5432/signalforge_test"
os.environ["DATABASE_URL"] = _test_url
os.environ["INGEST_USE_TEST_ADAPTER"] = "1"  # Enable TestAdapter for run_ingest_daily tests
os.environ.setdefault("SECRET_KEY", TEST_SECRET_KEY)
os.environ.setdefault("INTERNAL_JOB_TOKEN", TEST_INTERNAL_JOB_TOKEN)


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def client_with_db(db: Session) -> TestClient:
    """TestClient with get_db overridden to use the test db session (for integration tests)."""
    from app.main import app
    from app.db.session import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session")
def _ensure_migrations() -> None:
    """Create test DB if needed and run migrations once per test session."""
    import subprocess
    import sys

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Create test database if it doesn't exist (CREATE DATABASE requires autocommit)
    _user = os.getenv("PGUSER") or os.getenv("USER") or "postgres"
    _create_db_url = f"postgresql+psycopg://{_user}@localhost:5432/postgres"
    from sqlalchemy import create_engine, text
    engine = create_engine(_create_db_url)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("CREATE DATABASE signalforge_test"))
    except Exception:
        pass  # DB may already exist
    finally:
        engine.dispose()

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
    """Database session for model tests. All changes are rolled back after each test."""
    from app.db import engine
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# Issue #189: fractional_cto_v1 pack - UUID varies by migration; query DB at runtime


@pytest.fixture
def fractional_cto_pack_id(db):
    """UUID of fractional_cto_v1 pack (Issue #189). Use for pack-scoped fixtures."""
    from app.models import SignalPack
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    if pack is None:
        pytest.skip("fractional_cto_v1 pack not found (run migration 20260223_signal_packs)")
    return pack.id
