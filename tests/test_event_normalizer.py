"""Tests for event normalizer (RawEvent -> SignalEvent + CompanyCreate)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core_taxonomy.loader import get_core_signal_ids
from app.ingestion.normalize import normalize_raw_event
from app.schemas.signal import RawEvent


def test_normalize_maps_fields_correctly() -> None:
    """normalize_raw_event maps RawEvent fields to signal_event_data and CompanyCreate."""
    raw = RawEvent(
        company_name="Acme Corp",
        domain="acme.example.com",
        website_url="https://acme.example.com",
        event_type_candidate="funding_raised",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
        title="Series A",
        summary="Raised $10M",
        url="https://crunchbase.com/round/acme",
        source_event_id="cb-123",
        raw_payload={"amount": 10000000},
    )
    result = normalize_raw_event(raw, source="crunchbase")
    assert result is not None
    event_data, company_create = result

    assert event_data["source"] == "crunchbase"
    assert event_data["source_event_id"] == "cb-123"
    assert event_data["event_type"] == "funding_raised"
    assert event_data["event_time"] == raw.event_time
    assert event_data["title"] == "Series A"
    assert event_data["summary"] == "Raised $10M"
    assert event_data["url"] == "https://crunchbase.com/round/acme"
    assert event_data["raw"] == {"amount": 10000000}
    assert event_data["confidence"] == 0.7

    assert company_create.company_name == "Acme Corp"
    assert company_create.website_url == "https://acme.example.com"


def test_normalize_builds_company_create_from_domain() -> None:
    """When only domain is provided, website_url is derived."""
    raw = RawEvent(
        company_name="Beta Inc",
        domain="beta.io",
        event_type_candidate="job_posted_engineering",
        event_time=datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, source="producthunt")
    assert result is not None
    _, company_create = result
    assert company_create.company_name == "Beta Inc"
    assert company_create.website_url == "https://beta.io"


def test_normalize_builds_company_create_from_company_profile_url() -> None:
    """company_profile_url used as website_url when no domain/website_url."""
    raw = RawEvent(
        company_name="Gamma LLC",
        company_profile_url="https://gamma.com",
        event_type_candidate="launch_major",
        event_time=datetime(2026, 2, 18, 14, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, source="manual")
    assert result is not None
    _, company_create = result
    assert company_create.website_url == "https://gamma.com"


def test_normalize_extracts_linkedin_url() -> None:
    """LinkedIn URLs in company_profile_url map to company_linkedin_url."""
    raw = RawEvent(
        company_name="Delta Co",
        company_profile_url="https://linkedin.com/company/delta",
        event_type_candidate="cto_role_posted",
        event_time=datetime(2026, 2, 18, 9, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, source="manual")
    assert result is not None
    _, company_create = result
    assert "linkedin" in (company_create.company_linkedin_url or "").lower()


def test_normalize_rejects_invalid_event_type() -> None:
    """Unknown event_type_candidate returns None."""
    raw = RawEvent(
        company_name="Acme",
        event_type_candidate="unknown_event_type",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, source="test")
    assert result is None


def test_normalize_accepts_all_known_event_types() -> None:
    """All core taxonomy signal_ids and legacy ingest-only types are accepted (Milestone 6)."""
    accepted = get_core_signal_ids() | frozenset({"incorporation"})
    for event_type in accepted:
        raw = RawEvent(
            company_name="Test Co",
            event_type_candidate=event_type,
            event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
        )
        result = normalize_raw_event(raw, source="test")
        assert result is not None, f"event_type {event_type} should be accepted"
        event_data, _ = result
        assert event_data["event_type"] == event_type


def test_normalize_default_confidence() -> None:
    """Confidence defaults to 0.7."""
    raw = RawEvent(
        company_name="Acme",
        event_type_candidate="funding_raised",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, source="test")
    assert result is not None
    event_data, _ = result
    assert event_data["confidence"] == 0.7


def test_normalize_accepts_core_taxonomy_without_pack() -> None:
    """With pack=None, event types from core taxonomy are accepted (Issue #285, Milestone 4)."""
    core_ids = get_core_signal_ids()
    assert core_ids, "Core taxonomy must define signal_ids"
    for event_type in ("funding_raised", "repo_activity", "cto_role_posted"):
        assert event_type in core_ids
        raw = RawEvent(
            company_name="Test Co",
            event_type_candidate=event_type,
            event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
        )
        result = normalize_raw_event(raw, source="test", pack=None)
        assert result is not None, f"Core type {event_type} should be accepted with pack=None"
        event_data, _ = result
        assert event_data["event_type"] == event_type


def test_normalize_accepts_legacy_event_type_without_pack() -> None:
    """With pack=None, legacy types (e.g. incorporation) still accepted for backward compat."""
    raw = RawEvent(
        company_name="Acme Inc",
        event_type_candidate="incorporation",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, source="delaware_socrata", pack=None)
    assert result is not None, "incorporation (legacy) should be accepted with pack=None"
    event_data, _ = result
    assert event_data["event_type"] == "incorporation"


def test_normalize_with_pack_no_taxonomy_uses_core() -> None:
    """When pack has no taxonomy signal_ids, validation uses core taxonomy (Milestone 4)."""
    class MockPackNoTaxonomy:
        taxonomy = None

    raw = RawEvent(
        company_name="Acme",
        event_type_candidate="launch_major",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
    )
    result = normalize_raw_event(raw, source="test", pack=MockPackNoTaxonomy())
    assert result is not None
    event_data, _ = result
    assert event_data["event_type"] == "launch_major"
