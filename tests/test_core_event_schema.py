"""Tests for Core Event schema and validation (Extractor M1 — Issue #277).

Unit tests: valid/invalid event_type, null fields, source_refs present,
schema validation. Validator uses core taxonomy only.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core_taxonomy.loader import get_core_signal_ids
from app.extractor.validation import is_valid_core_event_type
from app.schemas.core_events import (
    CoreEventCandidate,
    ExtractionEntityCompany,
    ExtractionEntityPerson,
    get_events_from_payload,
)

# --- is_valid_core_event_type ---


def test_is_valid_core_event_type_accepts_core_signal_ids() -> None:
    """Known core signal_ids are valid event types."""
    for signal_id in get_core_signal_ids():
        assert is_valid_core_event_type(signal_id) is True


def test_is_valid_core_event_type_rejects_unknown() -> None:
    """Unknown event types are rejected."""
    assert is_valid_core_event_type("unknown_foo") is False
    assert is_valid_core_event_type("") is False
    assert is_valid_core_event_type("funding_raised_extra") is False


def test_is_valid_core_event_type_rejects_empty_string() -> None:
    """Empty string is not a valid event type."""
    assert is_valid_core_event_type("") is False


# --- CoreEventCandidate ---


def test_core_event_candidate_valid_minimal() -> None:
    """CoreEventCandidate accepts minimal valid fields with valid event_type."""
    # Use a known core signal_id
    obj = CoreEventCandidate(
        event_type="funding_raised",
        event_time=None,
        title=None,
        summary=None,
        url=None,
        confidence=0.9,
        source_refs=[0],
    )
    assert obj.event_type == "funding_raised"
    assert obj.confidence == 0.9
    assert obj.source_refs == [0]


def test_core_event_candidate_valid_full() -> None:
    """CoreEventCandidate accepts all fields populated."""
    now = datetime.now(UTC)
    obj = CoreEventCandidate(
        event_type="cto_role_posted",
        event_time=now,
        title="CTO role posted",
        summary="Company is hiring a CTO.",
        url="https://example.com/jobs",
        confidence=0.85,
        source_refs=[0, 1],
    )
    assert obj.event_type == "cto_role_posted"
    assert obj.event_time == now
    assert obj.title == "CTO role posted"
    assert obj.source_refs == [0, 1]


def test_core_event_candidate_rejects_unknown_event_type() -> None:
    """CoreEventCandidate rejects event_type not in core taxonomy."""
    with pytest.raises(ValidationError) as exc_info:
        CoreEventCandidate(
            event_type="not_in_taxonomy",
            event_time=None,
            title=None,
            summary=None,
            url=None,
            confidence=0.5,
            source_refs=[0],
        )
    errors = exc_info.value.errors()
    assert any("event_type" in (e.get("loc") or ()) for e in errors)


def test_core_event_candidate_requires_source_refs() -> None:
    """CoreEventCandidate requires source_refs (can be empty list for source-backed contract)."""
    # Plan: "all fields/events mapped to source_ids". Empty list is allowed for "no sources" candidate
    obj = CoreEventCandidate(
        event_type="funding_raised",
        event_time=None,
        title=None,
        summary=None,
        url=None,
        confidence=0.5,
        source_refs=[],
    )
    assert obj.source_refs == []


def test_core_event_candidate_confidence_bounds() -> None:
    """Confidence must be in [0, 1]."""
    CoreEventCandidate(
        event_type="funding_raised",
        event_time=None,
        title=None,
        summary=None,
        url=None,
        confidence=0.0,
        source_refs=[],
    )
    CoreEventCandidate(
        event_type="funding_raised",
        event_time=None,
        title=None,
        summary=None,
        url=None,
        confidence=1.0,
        source_refs=[],
    )
    with pytest.raises(ValidationError):
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=None,
            title=None,
            summary=None,
            url=None,
            confidence=1.1,
            source_refs=[],
        )
    with pytest.raises(ValidationError):
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=None,
            title=None,
            summary=None,
            url=None,
            confidence=-0.1,
            source_refs=[],
        )


def test_core_event_candidate_extra_forbid() -> None:
    """CoreEventCandidate forbids extra fields."""
    with pytest.raises(ValidationError):
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=None,
            title=None,
            summary=None,
            url=None,
            confidence=0.5,
            source_refs=[],
            extra_field="not_allowed",
        )


# --- ExtractionEntityCompany ---


def test_extraction_entity_company_nullable_fields() -> None:
    """ExtractionEntityCompany allows nullable fields per plan."""
    obj = ExtractionEntityCompany(
        name="Acme Inc",
        domain=None,
        website_url=None,
    )
    assert obj.name == "Acme Inc"
    assert obj.domain is None
    assert obj.website_url is None


def test_extraction_entity_company_full() -> None:
    """ExtractionEntityCompany accepts all fields."""
    obj = ExtractionEntityCompany(
        name="Acme Inc",
        domain="acme.com",
        website_url="https://acme.com",
    )
    assert obj.domain == "acme.com"
    assert obj.website_url == "https://acme.com"


# --- ExtractionEntityPerson ---


def test_extraction_entity_person_nullable_fields() -> None:
    """ExtractionEntityPerson allows nullable fields."""
    obj = ExtractionEntityPerson(
        name="Jane Doe",
        role=None,
    )
    assert obj.name == "Jane Doe"
    assert obj.role is None


def test_extraction_entity_person_full() -> None:
    """ExtractionEntityPerson accepts role."""
    obj = ExtractionEntityPerson(
        name="Jane Doe",
        role="CTO",
    )
    assert obj.role == "CTO"


# --- get_events_from_payload (M2 payload key compatibility) ---


def test_get_events_from_payload_returns_events_key() -> None:
    """get_events_from_payload returns list from 'events' when present."""
    payload = {"events": [{"event_type": "funding_raised", "confidence": 0.9}]}
    assert get_events_from_payload(payload) == [{"event_type": "funding_raised", "confidence": 0.9}]


def test_get_events_from_payload_returns_core_event_candidates_when_no_events() -> None:
    """get_events_from_payload returns list from 'core_event_candidates' when 'events' missing (M2)."""
    payload = {"core_event_candidates": [{"event_type": "cto_role_posted", "confidence": 0.8}]}
    assert get_events_from_payload(payload) == [
        {"event_type": "cto_role_posted", "confidence": 0.8}
    ]


def test_get_events_from_payload_prefers_events_over_core_event_candidates() -> None:
    """get_events_from_payload prefers 'events' when both keys present."""
    payload = {
        "events": [{"event_type": "funding_raised", "confidence": 0.9}],
        "core_event_candidates": [{"event_type": "other", "confidence": 0.5}],
    }
    assert get_events_from_payload(payload) == [{"event_type": "funding_raised", "confidence": 0.9}]


def test_get_events_from_payload_returns_empty_for_none_or_missing() -> None:
    """get_events_from_payload returns [] for None, empty dict, or non-list value."""
    assert get_events_from_payload(None) == []
    assert get_events_from_payload({}) == []
    assert get_events_from_payload({"events": "not-a-list"}) == []
    assert get_events_from_payload({"core_event_candidates": None}) == []


def test_get_events_from_payload_filters_non_dict_entries() -> None:
    """get_events_from_payload returns only list items that are dicts."""
    payload = {"events": [{"a": 1}, "skip", 0, None, {"b": 2}]}
    assert get_events_from_payload(payload) == [{"a": 1}, {"b": 2}]
