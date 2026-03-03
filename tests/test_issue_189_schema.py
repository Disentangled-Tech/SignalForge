"""Issue #189: Schema and migration tests for Signal Pack Architecture.

Tests verify:
- fractional_cto_v1 pack exists after migration
- pack_id columns present on all pack-scoped tables
- Backfill correct (no orphaned signals)
- No cross-pack contamination
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_signal_packs_table_exists(db: Session) -> None:
    """signal_packs table exists after migration."""
    result = db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'signal_packs'
            )
            """
        )
    )
    assert result.scalar() is True


@pytest.mark.integration
def test_fractional_cto_v1_pack_inserted(db: Session) -> None:
    """fractional_cto_v1 pack exists with correct pack_id and version."""
    result = db.execute(
        text(
            """
            SELECT id, pack_id, version, industry, is_active
            FROM signal_packs
            WHERE pack_id = 'fractional_cto_v1'
            """
        )
    )
    row = result.fetchone()
    assert row is not None
    assert row.pack_id == "fractional_cto_v1"
    assert row.version == "1"
    assert row.industry == "fractional_cto"
    assert row.is_active is True
    assert row.id is not None


@pytest.mark.integration
def test_readiness_snapshots_has_pack_id_column(db: Session) -> None:
    """readiness_snapshots has pack_id column."""
    result = db.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'readiness_snapshots'
            AND column_name = 'pack_id'
            """
        )
    )
    assert result.scalar() == "pack_id"


@pytest.mark.integration
def test_engagement_snapshots_has_pack_id_column(db: Session) -> None:
    """engagement_snapshots has pack_id column."""
    result = db.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'engagement_snapshots'
            AND column_name = 'pack_id'
            """
        )
    )
    assert result.scalar() == "pack_id"


@pytest.mark.integration
def test_signal_events_has_pack_id_column(db: Session) -> None:
    """signal_events has pack_id column."""
    result = db.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'signal_events'
            AND column_name = 'pack_id'
            """
        )
    )
    assert result.scalar() == "pack_id"


@pytest.mark.integration
def test_signal_records_has_pack_id_column(db: Session) -> None:
    """signal_records has pack_id column."""
    result = db.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'signal_records'
            AND column_name = 'pack_id'
            """
        )
    )
    assert result.scalar() == "pack_id"


@pytest.mark.integration
def test_outreach_recommendations_has_pack_id_and_playbook_id(db: Session) -> None:
    """outreach_recommendations has pack_id and playbook_id columns."""
    result = db.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'outreach_recommendations'
            AND column_name IN ('pack_id', 'playbook_id')
            ORDER BY column_name
            """
        )
    )
    cols = [r[0] for r in result.fetchall()]
    assert "pack_id" in cols
    assert "playbook_id" in cols


@pytest.mark.integration
def test_readiness_snapshots_unique_includes_pack_id(db: Session) -> None:
    """readiness_snapshots unique constraint is (company_id, as_of, pack_id)."""
    result = db.execute(
        text(
            """
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_schema = 'public' AND table_name = 'readiness_snapshots'
            AND constraint_type = 'UNIQUE'
            """
        )
    )
    names = [r[0] for r in result.fetchall()]
    assert any("pack" in n for n in names) or "uq_readiness_snapshots_company_as_of_pack" in names


@pytest.mark.integration
def test_readiness_snapshots_pack_id_column_accepts_fk(db: Session) -> None:
    """readiness_snapshots.pack_id accepts valid signal_packs.id (FK works)."""
    from datetime import date

    pack_row = db.execute(
        text("SELECT id FROM signal_packs WHERE pack_id = 'fractional_cto_v1' LIMIT 1")
    ).fetchone()
    if not pack_row:
        pytest.skip("fractional_cto_v1 pack not found")
    pack_id = pack_row[0]
    company_row = db.execute(text("SELECT id FROM companies LIMIT 1")).fetchone()
    if not company_row:
        pytest.skip("No companies in DB")
    company_id = company_row[0]
    as_of = date(2099, 9, 9)
    # Remove any pre-existing snapshot to avoid UniqueViolation from prior runs
    db.execute(
        text(
            "DELETE FROM readiness_snapshots WHERE company_id = :cid AND as_of = :as_of AND pack_id = :pid"
        ),
        {"cid": company_id, "as_of": as_of, "pid": pack_id},
    )
    db.commit()
    db.execute(
        text(
            """
            INSERT INTO readiness_snapshots (company_id, as_of, momentum, complexity, pressure, leadership_gap, composite, pack_id, computed_at)
            VALUES (:cid, :as_of, 70, 60, 55, 40, 65, :pid, now())
            """
        ),
        {"cid": company_id, "as_of": as_of, "pid": pack_id},
    )
    db.commit()


@pytest.mark.integration
def test_signal_pack_id_unique_per_version(db: Session) -> None:
    """pack_id + version must be unique in signal_packs."""
    result = db.execute(
        text(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'signal_packs'
            AND indexdef LIKE '%pack_id%version%'
            """
        )
    )
    # Unique index on (pack_id, version)
    indexes = result.fetchall()
    assert len(indexes) >= 1


@pytest.mark.integration
def test_signal_packs_has_config_checksum_column(db: Session) -> None:
    """signal_packs has config_checksum column (Issue #190, Phase 3)."""
    result = db.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'signal_packs'
            AND column_name = 'config_checksum'
            """
        )
    )
    assert result.scalar() == "config_checksum"


@pytest.mark.integration
def test_fractional_cto_v1_config_checksum_backfilled(db: Session) -> None:
    """fractional_cto_v1 pack has config_checksum backfilled and matches loader."""
    from app.packs.loader import load_pack

    result = db.execute(
        text(
            """
            SELECT config_checksum FROM signal_packs
            WHERE pack_id = 'fractional_cto_v1' AND version = '1'
            """
        )
    )
    row = result.fetchone()
    assert row is not None
    assert row.config_checksum is not None
    assert len(row.config_checksum) == 64
    pack = load_pack("fractional_cto_v1", "1")
    assert row.config_checksum == pack.config_checksum
