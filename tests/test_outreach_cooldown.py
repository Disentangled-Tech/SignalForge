"""Tests for outreach cooldown enforcement (Issue #109)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.company import Company
from app.services.outreach_history import (
    OutreachCooldownBlockedError,
    check_outreach_cooldown,
    create_outreach_record,
)


def test_cooldown_blocks_when_last_outreach_under_60_days(db: Session) -> None:
    """Last outreach 10 days ago → new record blocked."""
    company = Company(name="Cooldown Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    ten_days_ago = as_of - timedelta(days=10)
    create_outreach_record(
        db,
        company_id=company.id,
        sent_at=ten_days_ago,
        outreach_type="email",
        message=None,
        notes=None,
    )

    with pytest.raises(OutreachCooldownBlockedError) as exc_info:
        create_outreach_record(
            db,
            company_id=company.id,
            sent_at=as_of,
            outreach_type="email",
            message=None,
            notes=None,
        )
    assert "10 days ago" in exc_info.value.reason
    assert "60 days" in exc_info.value.reason


def test_cooldown_allows_when_last_outreach_exactly_60_days(db: Session) -> None:
    """Last outreach exactly 60 days ago → new record allowed (boundary: use > not >=)."""
    company = Company(name="Boundary 60 Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    exactly_60_days_ago = as_of - timedelta(days=60)
    create_outreach_record(
        db,
        company_id=company.id,
        sent_at=exactly_60_days_ago,
        outreach_type="email",
        message=None,
        notes=None,
    )

    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=as_of,
        outreach_type="linkedin_dm",
        message=None,
        notes=None,
    )
    assert record.id is not None


def test_cooldown_allows_when_last_outreach_over_60_days(db: Session) -> None:
    """Last outreach 61 days ago → new record allowed."""
    company = Company(name="Allowed Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    sixty_one_days_ago = as_of - timedelta(days=61)
    create_outreach_record(
        db,
        company_id=company.id,
        sent_at=sixty_one_days_ago,
        outreach_type="email",
        message=None,
        notes=None,
    )

    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=as_of,
        outreach_type="linkedin_dm",
        message=None,
        notes=None,
    )
    assert record.id is not None


def test_declined_blocks_when_declined_within_180_days(db: Session) -> None:
    """Outcome=declined 100 days ago → new record blocked."""
    company = Company(name="Declined Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    hundred_days_ago = as_of - timedelta(days=100)
    create_outreach_record(
        db,
        company_id=company.id,
        sent_at=hundred_days_ago,
        outreach_type="email",
        message=None,
        notes=None,
        outcome="declined",
    )

    with pytest.raises(OutreachCooldownBlockedError) as exc_info:
        create_outreach_record(
            db,
            company_id=company.id,
            sent_at=as_of,
            outreach_type="email",
            message=None,
            notes=None,
        )
    assert "declined" in exc_info.value.reason
    assert "180 days" in exc_info.value.reason


def test_declined_allows_when_declined_exactly_180_days(db: Session) -> None:
    """Outcome=declined exactly 180 days ago → new record allowed (boundary: use > not >=)."""
    company = Company(name="Boundary 180 Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    exactly_180_days_ago = as_of - timedelta(days=180)
    create_outreach_record(
        db,
        company_id=company.id,
        sent_at=exactly_180_days_ago,
        outreach_type="email",
        message=None,
        notes=None,
        outcome="declined",
    )

    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=as_of,
        outreach_type="email",
        message=None,
        notes=None,
    )
    assert record.id is not None


def test_declined_allows_when_declined_over_180_days(db: Session) -> None:
    """Outcome=declined 181 days ago → new record allowed."""
    company = Company(name="Old Declined Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    hundred_eighty_one_days_ago = as_of - timedelta(days=181)
    create_outreach_record(
        db,
        company_id=company.id,
        sent_at=hundred_eighty_one_days_ago,
        outreach_type="email",
        message=None,
        notes=None,
        outcome="declined",
    )

    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=as_of,
        outreach_type="email",
        message=None,
        notes=None,
    )
    assert record.id is not None


def test_declined_allows_when_outcome_not_declined(db: Session) -> None:
    """Outcome=replied 50 days ago does NOT block (60-day rule still applies)."""
    company = Company(name="Replied Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    fifty_days_ago = as_of - timedelta(days=50)
    create_outreach_record(
        db,
        company_id=company.id,
        sent_at=fifty_days_ago,
        outreach_type="email",
        message=None,
        notes=None,
        outcome="replied",
    )

    # 60-day cooldown blocks (50 days < 60)
    with pytest.raises(OutreachCooldownBlockedError) as exc_info:
        create_outreach_record(
            db,
            company_id=company.id,
            sent_at=as_of,
            outreach_type="email",
            message=None,
            notes=None,
        )
    assert "50 days ago" in exc_info.value.reason


def test_first_outreach_always_allowed(db: Session) -> None:
    """No prior records → success."""
    company = Company(name="First Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=as_of,
        outreach_type="email",
        message=None,
        notes=None,
    )
    assert record.id is not None


def test_cooldown_uses_sent_at_from_new_record(db: Session) -> None:
    """Boundary: last outreach 61 days ago, new record sent_at = today → allowed."""
    company = Company(name="Boundary Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    sixty_one_days_ago = as_of - timedelta(days=61)
    create_outreach_record(
        db,
        company_id=company.id,
        sent_at=sixty_one_days_ago,
        outreach_type="email",
        message=None,
        notes=None,
    )

    # New record with sent_at = as_of (61 days after last) → allowed
    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=as_of,
        outreach_type="email",
        message=None,
        notes=None,
    )
    assert record.id is not None


def test_check_outreach_cooldown_returns_allowed_when_no_history(db: Session) -> None:
    """check_outreach_cooldown returns allowed=True when no prior outreach."""
    company = Company(name="No History Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    result = check_outreach_cooldown(
        db, company.id, datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    )
    assert result.allowed is True
    assert result.reason is None
