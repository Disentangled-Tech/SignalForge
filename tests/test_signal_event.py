"""SignalEvent model and CRUD tests."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Company, SignalEvent


def test_signal_event_model_creation(db: Session) -> None:
    """SignalEvent model can be instantiated with required fields; assert defaults."""
    event = SignalEvent(
        source="crunchbase",
        event_type="funding_raised",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
    )
    assert event.source == "crunchbase"
    assert event.event_type == "funding_raised"
    assert event.company_id is None
    assert event.source_event_id is None
    assert event.title is None
    assert event.summary is None
    assert event.url is None
    assert event.raw is None
    # Default 0.7 is applied at insert time
    db.add(event)
    db.commit()
    db.refresh(event)
    assert event.confidence == 0.7


def test_signal_event_company_relationship(db: Session) -> None:
    """Create event with company_id; assert relationship."""
    company = Company(name="Event Co", website_url="https://event.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    event = SignalEvent(
        company_id=company.id,
        source="producthunt",
        event_type="job_posted_engineering",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
        title="Senior Engineer",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    db.refresh(company)

    assert event.company_id == company.id
    assert event.company is company
    assert len(company.signal_events) == 1
    assert company.signal_events[0].title == "Senior Engineer"


def test_signal_event_unique_constraint_prevents_duplicate(db: Session) -> None:
    """Insert two events with same (source, source_event_id); second raises IntegrityError."""
    unique_id = f"cb-{uuid.uuid4().hex[:12]}"
    event1 = SignalEvent(
        source="crunchbase",
        source_event_id=unique_id,
        event_type="funding_raised",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
    )
    db.add(event1)
    db.commit()

    event2 = SignalEvent(
        source="crunchbase",
        source_event_id=unique_id,
        event_type="funding_raised",
        event_time=datetime(2026, 2, 18, 13, 0, 0, tzinfo=UTC),
    )
    db.add(event2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_signal_event_duplicate_allowed_when_source_event_id_null(
    db: Session,
) -> None:
    """Insert two events with source_event_id=None; both should succeed."""
    event1 = SignalEvent(
        source="manual",
        source_event_id=None,
        event_type="funding_raised",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
    )
    db.add(event1)
    db.commit()

    event2 = SignalEvent(
        source="manual",
        source_event_id=None,
        event_type="job_posted_engineering",
        event_time=datetime(2026, 2, 18, 13, 0, 0, tzinfo=UTC),
    )
    db.add(event2)
    db.commit()

    assert event1.id != event2.id
    assert event1.source_event_id is None
    assert event2.source_event_id is None
