"""Tests for manual outreach tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    update_outreach_outcome,
    update_outreach_record,
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
    assert "outcome" in columns
    assert "timing_quality_feedback" in columns
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
    """Records ordered by sent_at desc. Spaced 61+ days apart for cooldown."""
    company = Company(name="Order Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    base = datetime(2026, 2, 18, 14, 0, 0, tzinfo=timezone.utc)
    t1 = base - timedelta(days=132)
    t2 = base - timedelta(days=71)
    t3 = base - timedelta(days=10)

    create_outreach_record(db, company.id, t1, "email", "First", None)
    create_outreach_record(db, company.id, t2, "linkedin_dm", "Second", None)
    create_outreach_record(db, company.id, t3, "other", "Third", None)

    records = list_outreach_for_company(db, company.id)
    assert len(records) == 3
    assert records[0].sent_at == t3  # most recent first
    assert records[1].sent_at == t2
    assert records[2].sent_at == t1


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


def test_create_outreach_record_with_outcome(db: Session):
    """Outcome is persisted when provided."""
    company = Company(name="Outcome Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    sent_at = datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=sent_at,
        outreach_type="email",
        message=None,
        notes=None,
        outcome="declined",
    )

    assert record.outcome == "declined"


def test_update_outreach_outcome(db: Session):
    """update_outreach_outcome sets outcome on existing record."""
    company = Company(name="Update Outcome Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    sent_at = datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=sent_at,
        outreach_type="email",
        message=None,
        notes=None,
    )
    assert record.outcome is None

    updated = update_outreach_outcome(db, company.id, record.id, "replied")
    assert updated is not None
    assert updated.outcome == "replied"


def test_update_outreach_outcome_clears_when_empty(db: Session):
    """update_outreach_outcome clears outcome when passed empty string."""
    company = Company(name="Clear Outcome Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    sent_at = datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=sent_at,
        outreach_type="email",
        message=None,
        notes=None,
        outcome="declined",
    )
    assert record.outcome == "declined"

    updated = update_outreach_outcome(db, company.id, record.id, None)
    assert updated is not None
    assert updated.outcome is None


def test_update_outreach_outcome_not_found(db: Session):
    """update_outreach_outcome returns None when record not found."""
    company = Company(name="No Record Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    result = update_outreach_outcome(db, company.id, 99999, "replied")
    assert result is None


def test_create_outreach_record_with_timing_quality(db: Session):
    """timing_quality_feedback is persisted when provided (Issue #114)."""
    company = Company(name="Timing Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    sent_at = datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=sent_at,
        outreach_type="email",
        message=None,
        notes=None,
        timing_quality_feedback="good_timing",
    )

    assert record.timing_quality_feedback == "good_timing"


def test_update_outreach_record_notes_and_timing(db: Session):
    """update_outreach_record updates notes and timing_quality_feedback (Issue #114)."""
    company = Company(name="Update Full Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    sent_at = datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=sent_at,
        outreach_type="email",
        message=None,
        notes=None,
    )
    assert record.notes is None
    assert record.timing_quality_feedback is None

    updated = update_outreach_record(
        db,
        company_id=company.id,
        outreach_id=record.id,
        notes="Follow up next week",
        timing_quality_feedback="neutral",
    )
    assert updated is not None
    assert updated.notes == "Follow up next week"
    assert updated.timing_quality_feedback == "neutral"
