"""Tests for canonical signal schemas (Phase 4, Plan Step 4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ingestion.event_storage import store_signal_event
from app.ingestion.normalize import normalize_raw_event
from app.models import Company
from app.schemas.signal import RawEvent
from app.schemas.signals import (
    CompanySignalEventRead,
    to_company_signal_event_read,
)


def _mock_pack(signal_ids: list[str]):
    """Pack mock with configurable taxonomy signal_ids for normalize tests."""

    class MockPack:
        taxonomy = {"signal_ids": signal_ids}

    return MockPack()


def test_signal_event_to_company_signal_event_read(db: Session) -> None:
    """to_company_signal_event_read converts SignalEvent to CompanySignalEventRead."""
    company = Company(name="Acme", website_url="https://acme.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    source_event_id = f"schema-test-{uuid.uuid4().hex[:12]}"
    stored = store_signal_event(
        db,
        company_id=company.id,
        source="crunchbase",
        source_event_id=source_event_id,
        event_type="funding_raised",
        event_time=datetime(2026, 2, 20, 14, 0, 0, tzinfo=UTC),
        title="Series A",
        summary="Raised $10M",
        url="https://example.com/funding",
        confidence=0.85,
    )
    assert stored is not None

    schema = to_company_signal_event_read(stored)
    assert isinstance(schema, CompanySignalEventRead)
    assert schema.id == stored.id
    assert schema.company_id == company.id
    assert schema.source == "crunchbase"
    assert schema.source_event_id == source_event_id
    assert schema.event_type == "funding_raised"
    assert schema.title == "Series A"
    assert schema.summary == "Raised $10M"
    assert schema.url == "https://example.com/funding"
    assert schema.confidence == 0.85
    assert schema.pack_id is None


def test_signal_event_to_company_signal_event_read_with_pack_id(
    db: Session, fractional_cto_pack_id
) -> None:
    """to_company_signal_event_read preserves pack_id when set."""
    company = Company(name="Beta", website_url="https://beta.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    source_event_id = f"schema-pack-{uuid.uuid4().hex[:12]}"
    stored = store_signal_event(
        db,
        company_id=company.id,
        source="test",
        source_event_id=source_event_id,
        event_type="launch_major",
        event_time=datetime(2026, 2, 20, 15, 0, 0, tzinfo=UTC),
        pack_id=fractional_cto_pack_id,
    )
    assert stored is not None

    schema = to_company_signal_event_read(stored)
    assert schema.pack_id == fractional_cto_pack_id


def test_normalize_validates_event_type_against_pack() -> None:
    """normalize_raw_event validates event_type_candidate against pack taxonomy."""
    pack = _mock_pack(["funding_raised", "launch_major"])

    raw_valid = RawEvent(
        company_name="Acme",
        domain="acme.com",
        event_type_candidate="funding_raised",
        event_time=datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC),
    )
    result_valid = normalize_raw_event(raw_valid, "crunchbase", pack=pack)
    assert result_valid is not None
    event_data, _ = result_valid
    assert event_data["event_type"] == "funding_raised"

    raw_invalid = RawEvent(
        company_name="Beta",
        domain="beta.com",
        event_type_candidate="unknown_signal_type",
        event_time=datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC),
    )
    result_invalid = normalize_raw_event(raw_invalid, "crunchbase", pack=pack)
    assert result_invalid is None


def test_normalize_without_pack_uses_legacy_event_types() -> None:
    """normalize_raw_event without pack validates against core taxonomy and legacy ingest-only types."""
    raw = RawEvent(
        company_name="Acme",
        domain="acme.com",
        event_type_candidate="cto_role_posted",
        event_time=datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, "manual", pack=None)
    assert result is not None
    event_data, _ = result
    assert event_data["event_type"] == "cto_role_posted"


def test_normalize_accepts_core_type_when_pack_omits_it() -> None:
    """Core types (e.g. incorporation, repo_activity) are accepted even when pack taxonomy omits them."""

    # Mock pack that does NOT include incorporation or repo_activity
    class MockPack:
        taxonomy = {"signal_ids": ["funding_raised", "launch_major"]}

    pack = MockPack()

    for core_type in ("incorporation", "repo_activity"):
        raw = RawEvent(
            company_name="Acme Inc",
            domain=None,
            event_type_candidate=core_type,
            event_time=datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC),
        )
        result = normalize_raw_event(raw, "delaware_socrata", pack=pack)
        assert result is not None, f"Core type {core_type} should be accepted when pack omits it"
        event_data, _ = result
        assert event_data["event_type"] == core_type


def test_normalize_accepts_repo_activity_without_pack() -> None:
    """normalize_raw_event(raw_repo_activity, pack=None) returns not None (Issue #244 Phase 1)."""
    raw = RawEvent(
        company_name="Acme",
        domain="acme.com",
        event_type_candidate="repo_activity",
        event_time=datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, "github", pack=None)
    assert result is not None
    event_data, _ = result
    assert event_data["event_type"] == "repo_activity"


def test_normalize_accepts_core_type_when_pack_omits_it() -> None:
    """Pack without repo_activity in taxonomy still accepts it (core type always accepted)."""
    pack = _mock_pack(["funding_raised", "launch_major"])
    raw = RawEvent(
        company_name="Acme",
        domain="acme.com",
        event_type_candidate="repo_activity",
        event_time=datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, "github", pack=pack)
    assert result is not None
    event_data, _ = result
    assert event_data["event_type"] == "repo_activity"


def test_normalize_accepts_incorporation_without_pack() -> None:
    """normalize_raw_event(raw_incorporation, pack=None) returns not None (Issue #250 Phase 1)."""
    raw = RawEvent(
        company_name="Acme LLC",
        domain=None,
        event_type_candidate="incorporation",
        event_time=datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, "delaware_socrata", pack=None)
    assert result is not None
    event_data, _ = result
    assert event_data["event_type"] == "incorporation"
