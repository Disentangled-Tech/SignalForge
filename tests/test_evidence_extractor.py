"""Tests for Evidence Extractor service (M2, Issue #277).

Unit: extract from EvidenceBundle; valid/invalid event types; source_refs present;
no signal derivation; pack-agnostic. Schema validation and unknown event type rejected.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.extractor.schemas import ExtractionResult, extraction_result_json_schema
from app.extractor.service import extract
from app.schemas.core_events import (
    CoreEventCandidate,
    ExtractionEntityCompany,
    ExtractionEntityPerson,
)
from app.schemas.scout import EvidenceBundle, EvidenceItem


def _make_bundle(
    company_name: str = "Acme Inc",
    website: str = "https://acme.com",
    evidence_count: int = 1,
) -> EvidenceBundle:
    items = [
        EvidenceItem(
            url="https://example.com/1",
            quoted_snippet="Snippet one",
            timestamp_seen=datetime.now(UTC),
            source_type="web",
            confidence_score=0.9,
        )
        for _ in range(evidence_count)
    ]
    return EvidenceBundle(
        candidate_company_name=company_name,
        company_website=website,
        why_now_hypothesis="",
        evidence=items if evidence_count else [],
        missing_information=[],
    )


# --- extract() rule-based (no raw_extraction) ---


def test_extract_returns_extraction_result() -> None:
    """extract(bundle) returns ExtractionResult."""
    bundle = _make_bundle()
    result = extract(bundle)
    assert isinstance(result, ExtractionResult)


def test_extract_builds_company_from_bundle() -> None:
    """Company is built from bundle candidate_company_name and company_website."""
    bundle = _make_bundle(company_name="Foo Corp", website="https://foo.com")
    result = extract(bundle)
    assert result.company is not None
    assert result.company.name == "Foo Corp"
    assert result.company.website_url == "https://foo.com"
    assert result.company.domain == "foo.com"


def test_extract_company_domain_none_when_website_not_parseable() -> None:
    """Domain can be None when website URL does not yield a host."""
    bundle = _make_bundle(website="https://")
    result = extract(bundle)
    assert result.company is not None
    assert result.company.website_url == "https://"
    assert result.company.domain is None


def test_extract_person_none_without_raw_extraction() -> None:
    """Without raw_extraction, person is None."""
    bundle = _make_bundle()
    result = extract(bundle)
    assert result.person is None


def test_extract_core_event_candidates_empty_without_raw_extraction() -> None:
    """Without raw_extraction, core_event_candidates is empty."""
    bundle = _make_bundle()
    result = extract(bundle)
    assert result.core_event_candidates == []


def test_extract_pack_agnostic_same_bundle_same_output() -> None:
    """Same bundle produces same ExtractionResult (pack-agnostic)."""
    bundle = _make_bundle()
    r1 = extract(bundle)
    r2 = extract(bundle)
    assert r1.company == r2.company
    assert r1.person == r2.person
    assert r1.core_event_candidates == r2.core_event_candidates


# --- extract() with raw_extraction (valid) ---


def test_extract_with_valid_raw_extraction_core_events() -> None:
    """raw_extraction with valid core event types yields core_event_candidates."""
    bundle = _make_bundle(evidence_count=2)
    raw = {
        "company": None,
        "person": None,
        "core_event_candidates": [
            {
                "event_type": "funding_raised",
                "event_time": None,
                "title": "Raised seed",
                "summary": None,
                "url": None,
                "confidence": 0.8,
                "source_refs": [0],
            },
            {
                "event_type": "cto_role_posted",
                "event_time": None,
                "title": None,
                "summary": "CTO job posted",
                "url": "https://example.com/jobs",
                "confidence": 0.7,
                "source_refs": [1],
            },
        ],
    }
    result = extract(bundle, raw_extraction=raw)
    assert len(result.core_event_candidates) == 2
    assert result.core_event_candidates[0].event_type == "funding_raised"
    assert result.core_event_candidates[0].source_refs == [0]
    assert result.core_event_candidates[1].event_type == "cto_role_posted"
    assert result.core_event_candidates[1].source_refs == [1]


def test_extract_with_raw_extraction_rejects_unknown_event_type() -> None:
    """raw_extraction with unknown event_type is rejected (dropped or validation error)."""
    bundle = _make_bundle(evidence_count=1)
    raw = {
        "company": None,
        "person": None,
        "core_event_candidates": [
            {
                "event_type": "not_in_taxonomy",
                "event_time": None,
                "title": None,
                "summary": None,
                "url": None,
                "confidence": 0.5,
                "source_refs": [0],
            },
        ],
    }
    result = extract(bundle, raw_extraction=raw)
    # Unknown event types must be rejected: no such candidate in output
    assert len(result.core_event_candidates) == 0


def test_extract_with_raw_extraction_person() -> None:
    """raw_extraction can provide person entity."""
    bundle = _make_bundle()
    raw = {
        "company": None,
        "person": {"name": "Jane Doe", "role": "CTO"},
        "core_event_candidates": [],
    }
    result = extract(bundle, raw_extraction=raw)
    assert result.person is not None
    assert result.person.name == "Jane Doe"
    assert result.person.role == "CTO"


def test_extract_with_raw_extraction_company_override() -> None:
    """raw_extraction company can override bundle-derived company when provided."""
    bundle = _make_bundle(company_name="Scout Name", website="https://scout.com")
    raw = {
        "company": {
            "name": "Extracted Co",
            "domain": "extracted.com",
            "website_url": "https://extracted.com",
        },
        "person": None,
        "core_event_candidates": [],
    }
    result = extract(bundle, raw_extraction=raw)
    assert result.company is not None
    assert result.company.name == "Extracted Co"
    assert result.company.domain == "extracted.com"


def test_extract_caps_core_event_candidates_at_max() -> None:
    """raw_extraction core_event_candidates are capped at MAX_CORE_EVENT_CANDIDATES (50)."""
    from app.extractor.service import MAX_CORE_EVENT_CANDIDATES

    bundle = _make_bundle(evidence_count=1)
    # 51 valid candidates; only first 50 should be processed
    raw = {
        "company": None,
        "person": None,
        "core_event_candidates": [
            {
                "event_type": "funding_raised",
                "event_time": None,
                "title": None,
                "summary": None,
                "url": None,
                "confidence": 0.8,
                "source_refs": [0],
            }
            for _ in range(MAX_CORE_EVENT_CANDIDATES + 1)
        ],
    }
    result = extract(bundle, raw_extraction=raw)
    assert len(result.core_event_candidates) == MAX_CORE_EVENT_CANDIDATES


def test_extract_source_refs_bounds() -> None:
    """source_refs beyond evidence length are invalid; candidates with invalid refs dropped or refs trimmed."""
    bundle = _make_bundle(evidence_count=1)  # only index 0 valid
    raw = {
        "company": None,
        "person": None,
        "core_event_candidates": [
            {
                "event_type": "funding_raised",
                "event_time": None,
                "title": None,
                "summary": None,
                "url": None,
                "confidence": 0.8,
                "source_refs": [0],
            },
            {
                "event_type": "cto_role_posted",
                "event_time": None,
                "title": None,
                "summary": None,
                "url": None,
                "confidence": 0.7,
                "source_refs": [99],
            },
        ],
    }
    result = extract(bundle, raw_extraction=raw)
    # At least the valid one is present; invalid refs may drop candidate or be trimmed per impl
    assert len(result.core_event_candidates) >= 1
    assert result.core_event_candidates[0].event_type == "funding_raised"
    assert result.core_event_candidates[0].source_refs == [0]


# --- ExtractionResult schema ---


def test_extraction_result_serializable_to_structured_payload() -> None:
    """ExtractionResult can be serialized to dict for structured_payload."""
    bundle = _make_bundle()
    result = extract(bundle)
    payload = result.model_dump(mode="json")
    assert "company" in payload
    assert "person" in payload
    assert "core_event_candidates" in payload
    assert isinstance(payload["core_event_candidates"], list)


# --- JSON schema ---


def test_extraction_result_json_schema_export() -> None:
    """Strict JSON schema for extraction output is exported."""
    schema = extraction_result_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema or "$defs" in schema or "definitions" in schema


# --- No signal derivation ---


def test_extractor_does_not_import_deriver_engine() -> None:
    """Extractor module must not import deriver engine (no signal derivation)."""
    import app.extractor.service as mod

    assert "deriver" not in dir(mod)


def test_extract_returns_only_core_event_candidates_no_signal_instances() -> None:
    """extract returns ExtractionResult with core_event_candidates only; no SignalInstance."""
    bundle = _make_bundle()
    result = extract(bundle)
    for c in result.core_event_candidates:
        assert isinstance(c, CoreEventCandidate)
    assert isinstance(result.company, (ExtractionEntityCompany, type(None)))
    assert isinstance(result.person, (ExtractionEntityPerson, type(None)))
