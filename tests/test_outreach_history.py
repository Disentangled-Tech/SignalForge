"""Tests for manual outreach tracking."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.briefing_item import BriefingItem
from app.models.company import Company
from app.models.outreach_history import OutreachHistory
from app.services.outreach_history import (
    create_outreach_record,
    delete_outreach_record,
    get_draft_for_company,
    list_outreach_for_company,
)


# ── Migration test ────────────────────────────────────────────────────


def test_outreach_history_migration(db: Session):
    """Table exists after upgrade (migration runs in conftest)."""
    # Query the table to verify it exists
    result = db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'outreach_history' ORDER BY ordinal_position"
        )
    )
    columns = [row[0] for row in result]
    assert "id" in columns
    assert "company_id" in columns
    assert "outreach_type" in columns
    assert "sent_at" in columns
    assert "message" in columns
    assert "notes" in columns
    assert "created_at" in columns


# ── Service tests ────────────────────────────────────────────────────


def test_create_outreach_record(db: Session):
    """Can insert outreach record with message and notes."""
    company = Company(
        name="Test Co",
        source="manual",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    sent_at = datetime(2026, 2, 18, 14, 30, 0, tzinfo=timezone.utc)
    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=sent_at,
        outreach_type="email",
        message="Hi, I wanted to follow up...",
        notes="No response yet",
    )

    assert record.id is not None
    assert record.company_id == company.id
    assert record.outreach_type == "email"
    assert record.sent_at == sent_at
    assert record.message == "Hi, I wanted to follow up..."
    assert record.notes == "No response yet"


def test_create_outreach_record_minimal(db: Session):
    """Can insert with only required fields (message and notes optional)."""
    company = Company(name="Minimal Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    sent_at = datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=sent_at,
        outreach_type="linkedin_dm",
        message=None,
        notes=None,
    )

    assert record.id is not None
    assert record.message is None
    assert record.notes is None


def test_get_draft_for_company_returns_latest_briefing_message(db: Session):
    """get_draft_for_company returns latest BriefingItem.outreach_message when present."""
    from app.models.analysis_record import AnalysisRecord

    company = Company(name="Draft Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    analysis = AnalysisRecord(
        company_id=company.id,
        source_type="manual",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    # Create two briefing items; latest should win
    old_briefing = BriefingItem(
        company_id=company.id,
        analysis_id=analysis.id,
        outreach_message="Old draft message",
    )
    db.add(old_briefing)
    db.commit()

    new_briefing = BriefingItem(
        company_id=company.id,
        analysis_id=analysis.id,
        outreach_message="Latest draft for pre-fill",
    )
    db.add(new_briefing)
    db.commit()

    draft = get_draft_for_company(db, company.id)
    assert draft == "Latest draft for pre-fill"


def test_get_draft_for_company_returns_none_when_no_briefing(db: Session):
    """get_draft_for_company returns None when no BriefingItem exists."""
    company = Company(name="No Brief Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    draft = get_draft_for_company(db, company.id)
    assert draft is None


def test_get_draft_for_company_returns_none_when_outreach_message_empty(db: Session):
    """get_draft_for_company returns None when BriefingItem has no outreach_message."""
    from app.models.analysis_record import AnalysisRecord

    company = Company(name="Empty Draft Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    analysis = AnalysisRecord(company_id=company.id, source_type="manual")
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    briefing = BriefingItem(
        company_id=company.id,
        analysis_id=analysis.id,
        outreach_message=None,
    )
    db.add(briefing)
    db.commit()

    draft = get_draft_for_company(db, company.id)
    assert draft is None


def test_list_outreach_ordered(db: Session):
    """Records ordered by sent_at desc."""
    company = Company(name="Order Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    t1 = datetime(2026, 2, 17, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 18, 14, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 2, 16, 9, 0, 0, tzinfo=timezone.utc)

    create_outreach_record(db, company.id, t1, "email", "First", None)
    create_outreach_record(db, company.id, t2, "linkedin_dm", "Second", None)
    create_outreach_record(db, company.id, t3, "other", "Third", None)

    records = list_outreach_for_company(db, company.id)
    assert len(records) == 3
    assert records[0].sent_at == t2  # most recent first
    assert records[1].sent_at == t1
    assert records[2].sent_at == t3


def test_delete_outreach_record(db: Session):
    """delete_outreach_record removes record and returns True."""
    company = Company(name="Delete Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    record = create_outreach_record(
        db, company.id,
        datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc),
        "email", "To delete", None,
    )

    deleted = delete_outreach_record(db, company.id, record.id)
    assert deleted is True

    remaining = list_outreach_for_company(db, company.id)
    assert len(remaining) == 0


def test_delete_outreach_record_not_found(db: Session):
    """delete_outreach_record returns False when record not found."""
    company = Company(name="No Record Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    deleted = delete_outreach_record(db, company.id, 99999)
    assert deleted is False
