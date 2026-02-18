"""Tests for event normalizer (RawEvent -> SignalEvent + CompanyCreate)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.company import CompanyCreate, CompanySource
from app.schemas.signal import RawEvent
from app.ingestion.normalize import normalize_raw_event
from app.ingestion.event_types import SIGNAL_EVENT_TYPES


def test_normalize_maps_fields_correctly() -> None:
    """normalize_raw_event maps RawEvent fields to signal_event_data and CompanyCreate."""
    raw = RawEvent(
        company_name="Acme Corp",
        domain="acme.example.com",
        website_url="https://acme.example.com",
        event_type_candidate="funding_raised",
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc),
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
        event_time=datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc),
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
        event_time=datetime(2026, 2, 18, 14, 0, 0, tzinfo=timezone.utc),
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
        event_time=datetime(2026, 2, 18, 9, 0, 0, tzinfo=timezone.utc),
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
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    result = normalize_raw_event(raw, source="test")
    assert result is None


def test_normalize_accepts_all_known_event_types() -> None:
    """All SIGNAL_EVENT_TYPES are accepted."""
    for event_type in SIGNAL_EVENT_TYPES:
        raw = RawEvent(
            company_name="Test Co",
            event_type_candidate=event_type,
            event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc),
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
        event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    result = normalize_raw_event(raw, source="test")
    assert result is not None
    event_data, _ = result
    assert event_data["confidence"] == 0.7
