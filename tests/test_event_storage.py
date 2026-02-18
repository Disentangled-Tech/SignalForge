"""Tests for event storage with deduplication (Issue #89)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models import Company, SignalEvent
from app.ingestion.event_storage import store_signal_event


def test_store_new_event_returns_signal_event(db: Session) -> None:
    """Insert new event returns SignalEvent."""
    company = Company(name="Acme", website_url="https://acme.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    result = store_signal_event(
        db,
        company_id=company.id,
        source="crunchbase",
        source_event_id="cb-001",
        event_type="funding_raised",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert result is not None
    assert isinstance(result, SignalEvent)
    assert result.id is not None
    assert result.company_id == company.id
    assert result.source == "crunchbase"
    assert result.source_event_id == "cb-001"
    assert result.event_type == "funding_raised"


def test_store_duplicate_returns_none(db: Session) -> None:
    """Insert duplicate (source, source_event_id) returns None, no new row."""
    company = Company(name="Beta", website_url="https://beta.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    store_signal_event(
        db,
        company_id=company.id,
        source="producthunt",
        source_event_id="ph-123",
        event_type="launch_major",
        event_time=datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc),
    )
    initial_count = db.query(SignalEvent).filter(SignalEvent.source == "producthunt").count()

    result = store_signal_event(
        db,
        company_id=company.id,
        source="producthunt",
        source_event_id="ph-123",
        event_type="launch_major",
        event_time=datetime(2026, 2, 18, 11, 0, 0, tzinfo=timezone.utc),
    )
    assert result is None
    assert db.query(SignalEvent).filter(SignalEvent.source == "producthunt").count() == initial_count


def test_store_with_source_event_id_none_allows_multiple(db: Session) -> None:
    """source_event_id=None allows multiple inserts (no unique constraint)."""
    company = Company(name="Gamma", website_url="https://gamma.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    r1 = store_signal_event(
        db,
        company_id=company.id,
        source="manual",
        source_event_id=None,
        event_type="funding_raised",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    r2 = store_signal_event(
        db,
        company_id=company.id,
        source="manual",
        source_event_id=None,
        event_type="job_posted_engineering",
        event_time=datetime(2026, 2, 18, 13, 0, 0, tzinfo=timezone.utc),
    )
    assert r1 is not None
    assert r2 is not None
    assert r1.id != r2.id


def test_store_with_optional_fields(db: Session) -> None:
    """Optional fields (title, summary, url, raw, confidence) are stored."""
    company = Company(name="Delta", website_url="https://delta.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    result = store_signal_event(
        db,
        company_id=company.id,
        source="test",
        source_event_id="t-1",
        event_type="api_launched",
        event_time=datetime(2026, 2, 18, 14, 0, 0, tzinfo=timezone.utc),
        title="API v2",
        summary="Launched new API",
        url="https://delta.example.com/api",
        raw={"version": "2.0"},
        confidence=0.9,
    )
    assert result is not None
    assert result.title == "API v2"
    assert result.summary == "Launched new API"
    assert result.url == "https://delta.example.com/api"
    assert result.raw == {"version": "2.0"}
    assert result.confidence == 0.9
