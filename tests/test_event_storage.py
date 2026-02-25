"""Tests for event storage with deduplication (Issue #89, Issue #240)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ingestion.event_storage import store_signal_event
from app.models import Company, SignalEvent


def test_store_new_event_returns_signal_event(db: Session) -> None:
    """Insert new event returns SignalEvent."""
    company = Company(name="Acme", website_url="https://acme.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    # Use unique source_event_id to avoid collision with stale DB data
    source_event_id = f"cb-test-{uuid.uuid4().hex[:12]}"
    result = store_signal_event(
        db,
        company_id=company.id,
        source="crunchbase",
        source_event_id=source_event_id,
        event_type="funding_raised",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
    )
    assert result is not None
    assert isinstance(result, SignalEvent)
    assert result.id is not None
    assert result.company_id == company.id
    assert result.source == "crunchbase"
    assert result.source_event_id == source_event_id
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
        event_time=datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC),
    )
    initial_count = db.query(SignalEvent).filter(SignalEvent.source == "producthunt").count()

    result = store_signal_event(
        db,
        company_id=company.id,
        source="producthunt",
        source_event_id="ph-123",
        event_type="launch_major",
        event_time=datetime(2026, 2, 18, 11, 0, 0, tzinfo=UTC),
    )
    assert result is None
    assert db.query(SignalEvent).filter(SignalEvent.source == "producthunt").count() == initial_count


def test_duplicate_signal_event_insert(db: Session) -> None:
    """Duplicate (source, source_event_id) fails or is ignored per Issue #240.

    App path: store_signal_event returns None (ignored).
    DB path: direct insert raises IntegrityError (fails).
    """
    company = Company(name="DedupCo", website_url="https://dedup.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    source_event_id = f"dup-{uuid.uuid4().hex[:12]}"
    store_signal_event(
        db,
        company_id=company.id,
        source="test_dup",
        source_event_id=source_event_id,
        event_type="funding_raised",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
    )
    db.commit()

    # App-level: second insert returns None (ignored)
    result = store_signal_event(
        db,
        company_id=company.id,
        source="test_dup",
        source_event_id=source_event_id,
        event_type="launch_major",
        event_time=datetime(2026, 2, 18, 13, 0, 0, tzinfo=UTC),
    )
    assert result is None

    # DB-level: direct insert of duplicate raises IntegrityError (Issue #240)
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                """
                INSERT INTO signal_events
                (company_id, source, source_event_id, event_type, event_time, ingested_at)
                VALUES (:cid, :src, :eid, 'job_posted', :et, now())
                """
            ),
            {
                "cid": company.id,
                "src": "test_dup",
                "eid": source_event_id,
                "et": datetime(2026, 2, 18, 14, 0, 0, tzinfo=UTC),
            },
        )
        db.commit()


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
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
    )
    r2 = store_signal_event(
        db,
        company_id=company.id,
        source="manual",
        source_event_id=None,
        event_type="job_posted_engineering",
        event_time=datetime(2026, 2, 18, 13, 0, 0, tzinfo=UTC),
    )
    assert r1 is not None
    assert r2 is not None
    assert r1.id != r2.id


def test_store_with_pack_id(db: Session, fractional_cto_pack_id) -> None:
    """pack_id is stored when provided (Issue #189)."""
    company = Company(name="Epsilon", website_url="https://epsilon.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    source_event_id = f"t-pack-{uuid.uuid4().hex[:12]}"
    result = store_signal_event(
        db,
        company_id=company.id,
        source="test",
        source_event_id=source_event_id,
        event_type="api_launched",
        event_time=datetime(2026, 2, 18, 15, 0, 0, tzinfo=UTC),
        pack_id=fractional_cto_pack_id,
    )
    assert result is not None
    assert result.pack_id == fractional_cto_pack_id


def test_store_with_optional_fields(db: Session) -> None:
    """Optional fields (title, summary, url, raw, confidence) are stored."""
    company = Company(name="Delta", website_url="https://delta.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    source_event_id = f"t-opt-{uuid.uuid4().hex[:12]}"
    result = store_signal_event(
        db,
        company_id=company.id,
        source="test",
        source_event_id=source_event_id,
        event_type="api_launched",
        event_time=datetime(2026, 2, 18, 14, 0, 0, tzinfo=UTC),
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
