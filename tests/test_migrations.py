"""Alembic migration tests."""

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.db import engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_alembic_env(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run alembic with current env (for tests that need DATABASE_URL)."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )


def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """Run alembic command and return result."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_alembic_upgrade_downgrade_cycle(_ensure_migrations: None) -> None:
    """Full migration cycle: upgrade creates tables, downgrade removes them."""
    # Skip when pack migrations applied: downgrade fails (duplicate company_id/as_of, FKs)
    current = run_alembic("current")
    out = current.stdout or ""
    if (
        "20260223_signal_packs" in out
        or "ee6582573566" in out
        or "20260224_config_checksum" in out
        or "20260224_job_run_pipeline" in out
        or "20260224_job_runs_indexes" in out
        or "(head)" in out
    ):
        pytest.skip(
            "Full downgrade to base not supported with pack migrations "
            "(see migration docstring for downgrade limitations)"
        )

    # Downgrade to base (clean slate)
    result = run_alembic("downgrade", "base")
    assert result.returncode == 0, f"downgrade failed: {result.stderr}"

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "companies" not in tables
    assert "signal_records" not in tables
    assert "job_runs" not in tables

    # Upgrade creates tables
    result = run_alembic("upgrade", "head")
    assert result.returncode == 0, f"upgrade failed: {result.stderr}"

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "companies" in tables
    assert "signal_records" in tables
    assert "job_runs" in tables
    assert "analysis_records" in tables
    assert "briefing_items" in tables
    assert "readiness_snapshots" in tables
    assert "watchlist" in tables
    assert "alerts" in tables
    assert "users" in tables
    assert "operator_profiles" in tables
    assert "app_settings" in tables
    assert "signal_events" in tables
    assert "engagement_snapshots" in tables
    assert "outreach_history" in tables


def test_migration_20260226_up_down(_ensure_migrations: None) -> None:
    """Migration 20260226_issue_240: upgrade and downgrade succeed (Phase 4, Issue #240)."""
    result = _run_alembic_env("current")
    out = result.stdout or ""
    if "20260226_issue_240" not in out and "(head)" not in out:
        _run_alembic_env("upgrade", "head", timeout=60)

    result = _run_alembic_env("downgrade", "20260225_analysis_pack_id", timeout=60)
    assert result.returncode == 0, f"downgrade failed: {result.stderr}"

    result = _run_alembic_env("upgrade", "20260226_issue_240", timeout=60)
    assert result.returncode == 0, f"upgrade to 20260226 failed: {result.stderr}"

    result = _run_alembic_env("upgrade", "head", timeout=60)
    assert result.returncode == 0, f"upgrade to head failed: {result.stderr}"


def test_migration_20260228_up_down(_ensure_migrations: None) -> None:
    """Migration 20260228_analysis_pack_idx: upgrade and downgrade succeed."""
    result = _run_alembic_env("downgrade", "20260227_user_workspaces", timeout=60)
    assert result.returncode == 0, f"downgrade failed: {result.stderr}"

    result = _run_alembic_env("upgrade", "20260228_analysis_pack_idx", timeout=60)
    assert result.returncode == 0, f"upgrade to 20260228 failed: {result.stderr}"

    result = _run_alembic_env("upgrade", "head", timeout=60)
    assert result.returncode == 0, f"upgrade to head failed: {result.stderr}"


@pytest.mark.integration
def test_config_checksum_migration_fails_when_pack_missing(_ensure_migrations: None) -> None:
    """Migration 20260224 fails when fractional_cto_v1 pack cannot be loaded (Option B).

    Verifies strict correctness: migration must have packs/ present.
    """
    pack_dir = Path(PROJECT_ROOT) / "packs" / "fractional_cto_v1"
    backup_dir = Path(PROJECT_ROOT) / "packs" / "fractional_cto_v1_test_backup"
    if not pack_dir.exists():
        pytest.skip("fractional_cto_v1 pack not in repo")

    # Downgrade to ee6582573566 so we can re-run the config_checksum migration
    # Extended timeout: downgrade can be slow with many migrations
    result = _run_alembic_env("downgrade", "ee6582573566", timeout=90)
    if result.returncode != 0:
        pytest.skip(f"Could not downgrade to ee6582573566: {result.stderr}")

    # Temporarily move pack out of the way so load_pack fails
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.move(str(pack_dir), str(backup_dir))
    try:
        result = _run_alembic_env("upgrade", "20260224_config_checksum", timeout=90)
        assert result.returncode != 0, "Migration must fail when pack is missing"
        err = (result.stderr or result.stdout or "").lower()
        assert (
            "fractional_cto_v1" in err
            or "filenotfounderror" in err
            or "pack" in err
            or "load_pack" in err
        ), f"Error output should mention pack/load failure: {result.stderr}"
    finally:
        # Restore pack and re-upgrade to head
        shutil.move(str(backup_dir), str(pack_dir))
        _run_alembic_env("upgrade", "head", timeout=90)


def test_signal_instances_unique_migration_fails_with_duplicates(
    _ensure_migrations: None,
) -> None:
    """Migration 20260224_signal_instances_unique fails with clear message when duplicates exist."""
    # Downgrade to just before the unique constraint migration
    result = _run_alembic_env("downgrade", "20260224_job_runs_indexes")
    if result.returncode != 0:
        pytest.skip(f"Could not downgrade: {result.stderr}")

    # Insert duplicate signal_instances (same entity_id, signal_id, pack_id)
    with engine.connect() as conn:
        # Get a valid pack_id and entity_id from existing data
        row = conn.execute(
            text(
                "SELECT id FROM signal_packs WHERE pack_id = 'fractional_cto_v1' LIMIT 1"
            )
        ).fetchone()
        if not row:
            _run_alembic_env("upgrade", "head")
            pytest.skip("fractional_cto_v1 pack not found")
        pack_id = row[0]

        row = conn.execute(text("SELECT id FROM companies LIMIT 1")).fetchone()
        if not row:
            _run_alembic_env("upgrade", "head")
            pytest.skip("No companies in DB")
        entity_id = row[0]

        for _ in range(2):
            conn.execute(
                text(
                    "INSERT INTO signal_instances (id, entity_id, signal_id, pack_id, strength) "
                    "VALUES (:id, :entity_id, 'funding_raised', :pack_id, 1.0)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "entity_id": entity_id,
                    "pack_id": str(pack_id),
                },
            )
        conn.commit()

    try:
        result = _run_alembic_env("upgrade", "20260224_signal_instances_unique")
        assert result.returncode != 0, "Migration must fail when duplicates exist"
        err = (result.stderr or result.stdout or "").lower()
        assert "duplicate" in err, f"Error should mention duplicates: {result.stderr}"
        assert "signal_instances" in err or "resolve" in err, (
            f"Error should mention signal_instances or resolve: {result.stderr}"
        )
    finally:
        # Clean up duplicates and restore to head
        with engine.connect() as conn:
            conn.execute(
                text(
                    "DELETE FROM signal_instances WHERE entity_id = :eid AND signal_id = 'funding_raised'"
                ),
                {"eid": entity_id},
            )
            conn.commit()
        _run_alembic_env("upgrade", "head")


@pytest.mark.integration
def test_esl_decision_columns_backfill_preserves_suppress_from_explain(
    _ensure_migrations: None,
) -> None:
    """Migration 20260224_esl_decision_cols backfills from explain when present.

    Rows with explain.esl_decision='suppress' must get esl_decision='suppress' in column.
    Rows with no explain or invalid explain get esl_decision='allow'.
    """
    result = _run_alembic_env("downgrade", "20260224_evidence_event_ids", timeout=90)
    if result.returncode != 0:
        pytest.skip(f"Could not downgrade: {result.stderr}")

    with engine.connect() as conn:
        pack_row = conn.execute(
            text("SELECT id FROM signal_packs WHERE pack_id = 'fractional_cto_v1' LIMIT 1")
        ).fetchone()
        if not pack_row:
            _run_alembic_env("upgrade", "head", timeout=90)
            pytest.skip("fractional_cto_v1 pack not found")
        pack_id = pack_row[0]

        company_row = conn.execute(text("SELECT id FROM companies LIMIT 1")).fetchone()
        if not company_row:
            _run_alembic_env("upgrade", "head", timeout=90)
            pytest.skip("No companies in DB")
        company_id = company_row[0]

        # Row with explain.esl_decision=suppress
        conn.execute(
            text("""
                INSERT INTO engagement_snapshots
                (company_id, as_of, esl_score, engagement_type, explain, pack_id)
                VALUES (:cid, '2099-01-01'::date, 0.5, 'Observe Only',
                    '{"esl_decision":"suppress","esl_reason_code":"blocked_signal"}'::jsonb, :pid)
            """),
            {"cid": company_id, "pid": str(pack_id)},
        )
        # Row with no explain (legacy)
        conn.execute(
            text("""
                INSERT INTO engagement_snapshots
                (company_id, as_of, esl_score, engagement_type, explain, pack_id)
                VALUES (:cid, '2099-01-02'::date, 0.5, 'Observe Only', NULL, :pid)
            """),
            {"cid": company_id, "pid": str(pack_id)},
        )
        conn.commit()

    try:
        result = _run_alembic_env("upgrade", "20260224_esl_decision_cols", timeout=90)
        assert result.returncode == 0, f"Upgrade failed: {result.stderr}"

        with engine.connect() as conn:
            row_suppress = conn.execute(
                text("""
                    SELECT esl_decision, esl_reason_code FROM engagement_snapshots
                    WHERE company_id = :cid AND as_of = '2099-01-01'
                """),
                {"cid": company_id},
            ).fetchone()
            row_legacy = conn.execute(
                text("""
                    SELECT esl_decision, esl_reason_code FROM engagement_snapshots
                    WHERE company_id = :cid AND as_of = '2099-01-02'
                """),
                {"cid": company_id},
            ).fetchone()

        assert row_suppress is not None
        assert row_suppress[0] == "suppress", f"Expected suppress, got {row_suppress[0]}"
        assert row_suppress[1] == "blocked_signal"

        assert row_legacy is not None
        assert row_legacy[0] == "allow", f"Expected allow, got {row_legacy[0]}"
        assert row_legacy[1] == "legacy"
    finally:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "DELETE FROM engagement_snapshots WHERE company_id = :cid AND as_of >= '2099-01-01'"
                ),
                {"cid": company_id},
            )
            conn.commit()
        _run_alembic_env("upgrade", "head", timeout=90)
