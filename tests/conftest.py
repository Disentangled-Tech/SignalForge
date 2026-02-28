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
os.environ.setdefault("WORKSPACE_JOB_RATE_LIMIT_PER_HOUR", "0")  # Disable for tests


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    from app.main import app

    return TestClient(app)


@pytest.fixture
def client_with_db(db: Session) -> TestClient:
    """TestClient with get_db overridden to use the test db session (for integration tests)."""
    from app.db.session import get_db
    from app.main import app

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _clear_core_loader_caches() -> None:
    """Clear lru_cache on core taxonomy and deriver loaders before and after each test.

    Prevents stale cache state from propagating between tests, particularly for
    tests that patch load_core_derivers or load_core_taxonomy to inject test data.
    Clearing both before and after ensures a clean slate regardless of test order.
    """
    from app.core_derivers.loader import (
        get_core_derivers_version,
        get_core_passthrough_map,
        get_core_pattern_derivers,
        load_core_derivers,
    )
    from app.core_taxonomy.loader import (
        get_core_signal_ids,
        get_core_taxonomy_version,
        load_core_taxonomy,
    )

    load_core_taxonomy.cache_clear()
    get_core_signal_ids.cache_clear()
    get_core_taxonomy_version.cache_clear()
    load_core_derivers.cache_clear()
    get_core_passthrough_map.cache_clear()
    get_core_pattern_derivers.cache_clear()
    get_core_derivers_version.cache_clear()
    yield
    load_core_taxonomy.cache_clear()
    get_core_signal_ids.cache_clear()
    get_core_taxonomy_version.cache_clear()
    load_core_derivers.cache_clear()
    get_core_passthrough_map.cache_clear()
    get_core_pattern_derivers.cache_clear()
    get_core_derivers_version.cache_clear()


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


@pytest.fixture
def core_pack_id(db):
    """UUID of core pack sentinel (Issue #287 M1). Use for derive output assertions."""
    from app.services.pack_resolver import get_core_pack_id

    core_id = get_core_pack_id(db)
    if core_id is None:
        pytest.skip("core pack not installed (run migration 20260226_core_pack_sentinel)")
    return core_id


@pytest.fixture
def bookkeeping_pack_id(db):
    """UUID of bookkeeping_v1 pack (Issue #175, Phase 3). Deprecated: use esl_blocked_pack_id or second_pack_id (Issue #289 M1)."""
    from app.models import SignalPack

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "bookkeeping_v1").first()
    if pack is None:
        pytest.skip("bookkeeping_v1 pack not found (run migration 20260224_bookkeeping_pack)")
    return pack.id


def _get_or_create_signal_pack(
    db, pack_id: str, version: str = "1", description: str | None = None
):
    """Get or create a SignalPack row; used by second_pack and esl_blocked_pack fixtures (Issue #289 M1)."""
    import uuid

    from app.models import SignalPack

    pack = (
        db.query(SignalPack)
        .filter(
            SignalPack.pack_id == pack_id,
            SignalPack.version == version,
        )
        .first()
    )
    if pack is not None:
        return pack
    pack = SignalPack(
        id=uuid.uuid4(),
        pack_id=pack_id,
        version=version,
        industry=None,
        description=description or f"{pack_id} test pack",
        is_active=True,
    )
    db.add(pack)
    db.commit()
    db.refresh(pack)
    return pack


@pytest.fixture
def second_pack(db):
    """SignalPack row for example_v2 (get or create). Use for pack isolation tests (Issue #289 M1)."""
    return _get_or_create_signal_pack(db, "example_v2", version="1", description="Example V2 pack")


@pytest.fixture
def second_pack_id(second_pack):
    """UUID of example_v2 pack. Use for lead_feed and pack-scoped tests (Issue #289 M1)."""
    return second_pack.id


@pytest.fixture
def esl_blocked_pack(db):
    """SignalPack row for example_esl_blocked (get or create). Use for ESL blocked_signal tests (Issue #289 M1)."""
    return _get_or_create_signal_pack(
        db, "example_esl_blocked", version="1", description="ESL blocked_signal test pack"
    )


@pytest.fixture
def esl_blocked_pack_id(esl_blocked_pack):
    """UUID of example_esl_blocked pack. Use for ESL gate tests (Issue #289 M1)."""
    return esl_blocked_pack.id
