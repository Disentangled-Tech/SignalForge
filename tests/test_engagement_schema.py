"""Tests for engagement schema (Issue #105)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.db import engine
from app.models.company import Company
from app.models.engagement_snapshot import EngagementSnapshot
from app.models.outreach_history import OutreachHistory


def test_engagement_snapshots_table_exists(_ensure_migrations: None) -> None:
    """Migration creates engagement_snapshots table."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "engagement_snapshots" in tables


def test_engagement_snapshots_unique_company_as_of(db) -> None:
    """Duplicate (company_id, as_of) raises IntegrityError."""
    company = Company(name="Test Co", source="manual")
    db.add(company)
    db.flush()

    snap1 = EngagementSnapshot(
        company_id=company.id,
        as_of=date(2026, 2, 18),
        esl_score=0.75,
        engagement_type="Soft Value Share",
    )
    db.add(snap1)
    db.commit()

    snap2 = EngagementSnapshot(
        company_id=company.id,
        as_of=date(2026, 2, 18),
        esl_score=0.5,
        engagement_type="Observe Only",
    )
    db.add(snap2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_outreach_history_insert(db) -> None:
    """Can insert outreach_history row (acceptance criteria)."""
    company = Company(name="Outreach Test Co", source="manual")
    db.add(company)
    db.flush()

    history = OutreachHistory(
        company_id=company.id,
        outreach_type="email",
        sent_at=datetime.now(timezone.utc),
        outcome="replied",
        notes="Positive response",
    )
    db.add(history)
    db.commit()

    assert history.id is not None
    assert history.company_id == company.id
    assert history.outreach_type == "email"
    assert history.outcome == "replied"


def test_alignment_flags_editable(db) -> None:
    """Can update alignment_ok_to_contact and alignment_notes on Company."""
    company = Company(name="Alignment Test Co", source="manual")
    db.add(company)
    db.commit()

    company.alignment_ok_to_contact = True
    company.alignment_notes = "Founder mission aligned; ND-friendly signals"
    db.commit()
    db.refresh(company)

    assert company.alignment_ok_to_contact is True
    assert company.alignment_notes == "Founder mission aligned; ND-friendly signals"


def test_migration_upgrade_downgrade_cycle(_ensure_migrations: None) -> None:
    """Upgrade creates engagement_snapshots and outreach_history; downgrade removes them."""
    import subprocess
    import sys

    import os

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Downgrade to base
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"downgrade failed: {result.stderr}"

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "engagement_snapshots" not in tables
    assert "outreach_history" not in tables

    # Upgrade to head
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"upgrade failed: {result.stderr}"

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "engagement_snapshots" in tables
    assert "outreach_history" in tables
