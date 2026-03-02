"""Tests for Structured Extraction Payload contract (Extractor M3 — Issue #277).

Unit tests: ExtractionClaim validation, StructuredExtractionPayload validation,
serialization to store-compatible dict, and compatibility with evidence store.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.evidence.store import store_evidence_bundle
from app.models.evidence_claim import EvidenceClaim
from app.schemas.core_events import (
    EXTRACTION_CLAIM_VALUE_MAX_LENGTH,
    CoreEventCandidate,
    ExtractionClaim,
    ExtractionEntityCompany,
    ExtractionEntityPerson,
    StructuredExtractionPayload,
)
from app.schemas.scout import EvidenceBundle, EvidenceItem

# --- ExtractionClaim ---


def test_extraction_claim_valid_minimal() -> None:
    """ExtractionClaim accepts minimal fields (entity_type, field; value/source_refs/confidence optional)."""
    c = ExtractionClaim(
        entity_type="company",
        field="name",
        value=None,
        source_refs=[],
        confidence=None,
    )
    assert c.entity_type == "company"
    assert c.field == "name"
    assert c.value is None
    assert c.source_refs == []
    assert c.confidence is None


def test_extraction_claim_valid_full() -> None:
    """ExtractionClaim accepts all fields with source_refs and confidence."""
    c = ExtractionClaim(
        entity_type="company",
        field="funding",
        value="Series A",
        source_refs=[0, 1],
        confidence=0.95,
    )
    assert c.value == "Series A"
    assert c.source_refs == [0, 1]
    assert c.confidence == 0.95


def test_extraction_claim_confidence_bounds() -> None:
    """ExtractionClaim confidence must be in [0, 1] when provided."""
    ExtractionClaim(
        entity_type="company",
        field="x",
        value=None,
        source_refs=[],
        confidence=0.0,
    )
    ExtractionClaim(
        entity_type="company",
        field="x",
        value=None,
        source_refs=[],
        confidence=1.0,
    )
    with pytest.raises(ValidationError):
        ExtractionClaim(
            entity_type="company",
            field="x",
            value=None,
            source_refs=[],
            confidence=1.1,
        )
    with pytest.raises(ValidationError):
        ExtractionClaim(
            entity_type="company",
            field="x",
            value=None,
            source_refs=[],
            confidence=-0.1,
        )


def test_extraction_claim_entity_type_field_max_length() -> None:
    """ExtractionClaim entity_type and field respect max length for DB."""
    ExtractionClaim(
        entity_type="a" * 64,
        field="b" * 255,
        value=None,
        source_refs=[],
        confidence=None,
    )
    with pytest.raises(ValidationError):
        ExtractionClaim(
            entity_type="a" * 65,
            field="x",
            value=None,
            source_refs=[],
            confidence=None,
        )
    with pytest.raises(ValidationError):
        ExtractionClaim(
            entity_type="x",
            field="b" * 256,
            value=None,
            source_refs=[],
            confidence=None,
        )


def test_extraction_claim_extra_forbid() -> None:
    """ExtractionClaim forbids extra fields."""
    with pytest.raises(ValidationError):
        ExtractionClaim(
            entity_type="company",
            field="name",
            value=None,
            source_refs=[],
            confidence=None,
            extra_key="not_allowed",
        )


def test_extraction_claim_value_max_length() -> None:
    """ExtractionClaim value accepts up to EXTRACTION_CLAIM_VALUE_MAX_LENGTH; rejects longer."""
    max_val = "x" * EXTRACTION_CLAIM_VALUE_MAX_LENGTH
    c = ExtractionClaim(
        entity_type="company",
        field="notes",
        value=max_val,
        source_refs=[],
        confidence=None,
    )
    assert c.value == max_val
    with pytest.raises(ValidationError):
        ExtractionClaim(
            entity_type="company",
            field="notes",
            value="x" * (EXTRACTION_CLAIM_VALUE_MAX_LENGTH + 1),
            source_refs=[],
            confidence=None,
        )


# --- StructuredExtractionPayload ---


def test_structured_extraction_payload_valid_empty() -> None:
    """StructuredExtractionPayload accepts empty events, persons, claims and no company."""
    p = StructuredExtractionPayload(
        version="1.0",
        events=[],
        company=None,
        persons=[],
        claims=[],
    )
    assert p.version == "1.0"
    assert p.events == []
    assert p.company is None
    assert p.persons == []
    assert p.claims == []


def test_structured_extraction_payload_valid_full() -> None:
    """StructuredExtractionPayload accepts events, company, persons, claims."""
    event = CoreEventCandidate(
        event_type="funding_raised",
        event_time=None,
        title=None,
        summary=None,
        url=None,
        confidence=0.9,
        source_refs=[0],
    )
    company = ExtractionEntityCompany(name="Acme", domain="acme.com", website_url=None)
    person = ExtractionEntityPerson(name="Jane", role="CTO")
    claim = ExtractionClaim(
        entity_type="company",
        field="funding",
        value="Series A",
        source_refs=[0],
        confidence=0.95,
    )
    p = StructuredExtractionPayload(
        version="1.0",
        events=[event],
        company=company,
        persons=[person],
        claims=[claim],
    )
    assert len(p.events) == 1
    assert p.events[0].event_type == "funding_raised"
    assert p.company is not None
    assert p.company.name == "Acme"
    assert len(p.persons) == 1
    assert p.persons[0].name == "Jane"
    assert len(p.claims) == 1
    assert p.claims[0].field == "funding"


def test_structured_extraction_payload_serialization_to_store_format() -> None:
    """StructuredExtractionPayload.model_dump(mode='json') produces store-compatible dict with claims."""
    claim = ExtractionClaim(
        entity_type="company",
        field="funding",
        value="Series A",
        source_refs=[0, 1],
        confidence=0.9,
    )
    p = StructuredExtractionPayload(
        version="1.0",
        events=[],
        company=None,
        persons=[],
        claims=[claim],
    )
    d = p.model_dump(mode="json")
    assert isinstance(d, dict)
    assert d.get("version") == "1.0"
    assert "claims" in d
    assert len(d["claims"]) == 1
    assert d["claims"][0]["entity_type"] == "company"
    assert d["claims"][0]["field"] == "funding"
    assert d["claims"][0]["value"] == "Series A"
    assert d["claims"][0]["source_refs"] == [0, 1]
    assert d["claims"][0]["confidence"] == 0.9


def test_structured_extraction_payload_extra_forbid() -> None:
    """StructuredExtractionPayload forbids extra fields."""
    with pytest.raises(ValidationError):
        StructuredExtractionPayload(
            version="1.0",
            events=[],
            company=None,
            persons=[],
            claims=[],
            extra_key="not_allowed",
        )


def test_structured_extraction_payload_default_version() -> None:
    """StructuredExtractionPayload has sensible default version."""
    p = StructuredExtractionPayload(
        events=[],
        company=None,
        persons=[],
        claims=[],
    )
    assert p.version == "1.0"


# --- Store compatibility (payload from schema works with store_evidence_bundle) ---


def _make_evidence_item(url: str, snippet: str) -> EvidenceItem:
    return EvidenceItem(
        url=url,
        quoted_snippet=snippet,
        timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
        source_type="web",
        confidence_score=0.9,
    )


def test_structured_payload_store_compatibility_claims_written(db: Session) -> None:
    """StructuredExtractionPayload.model_dump(mode='json') works with store_evidence_bundle; claims inserted."""
    bundle = EvidenceBundle(
        candidate_company_name="M3 Contract Co",
        company_website="https://m3.example.com",
        why_now_hypothesis="Funded.",
        evidence=[
            _make_evidence_item("https://example.com/s1", "snippet one"),
            _make_evidence_item("https://example.com/s2", "snippet two"),
        ],
    )
    payload = StructuredExtractionPayload(
        version="1.0",
        events=[],
        company=None,
        persons=[],
        claims=[
            ExtractionClaim(
                entity_type="company",
                field="funding",
                value="Series A",
                source_refs=[0],
                confidence=0.95,
            ),
            ExtractionClaim(
                entity_type="company",
                field="name",
                value="M3 Contract Co",
                source_refs=[0, 1],
                confidence=0.9,
            ),
        ],
    )
    records = store_evidence_bundle(
        db,
        run_id="run-m3-contract",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context={"run_id": "run-m3-contract"},
        raw_model_output=None,
        structured_payloads=[payload.model_dump(mode="json")],
    )
    assert len(records) == 1
    bundle_id = records[0].id
    claims = (
        db.query(EvidenceClaim)
        .filter(EvidenceClaim.bundle_id == bundle_id)
        .order_by(EvidenceClaim.id)
        .all()
    )
    assert len(claims) == 2
    assert claims[0].entity_type == "company"
    assert claims[0].field == "funding"
    assert claims[0].value == "Series A"
    assert claims[0].confidence == 0.95
    assert len(claims[0].source_ids or []) == 1
    assert claims[1].field == "name"
    assert claims[1].value == "M3 Contract Co"
    assert len(claims[1].source_ids or []) == 2


def test_structured_payload_out_of_range_source_refs_store_truncates_to_valid(
    db: Session,
) -> None:
    """Store resolves only source_refs in range; out-of-range refs yield empty source_ids."""
    bundle = EvidenceBundle(
        candidate_company_name="OOR Co",
        company_website="https://oor.example.com",
        why_now_hypothesis="",
        evidence=[
            _make_evidence_item("https://example.com/a", "snippet a"),
            _make_evidence_item("https://example.com/b", "snippet b"),
        ],
    )
    # source_refs [5, 99] are beyond len(evidence)==2; store only resolves 0 <= ref < 2
    payload = StructuredExtractionPayload(
        version="1.0",
        events=[],
        company=None,
        persons=[],
        claims=[
            ExtractionClaim(
                entity_type="company",
                field="funding",
                value="Unknown",
                source_refs=[5, 99],
                confidence=0.5,
            ),
            ExtractionClaim(
                entity_type="company",
                field="name",
                value="OOR Co",
                source_refs=[0, 1],
                confidence=0.9,
            ),
        ],
    )
    records = store_evidence_bundle(
        db,
        run_id="run-oor",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context=None,
        raw_model_output=None,
        structured_payloads=[payload.model_dump(mode="json")],
    )
    assert len(records) == 1
    bundle_id = records[0].id
    claims = (
        db.query(EvidenceClaim)
        .filter(EvidenceClaim.bundle_id == bundle_id)
        .order_by(EvidenceClaim.id)
        .all()
    )
    assert len(claims) == 2
    # First claim: out-of-range refs -> store writes claim with empty source_ids
    assert claims[0].field == "funding"
    assert claims[0].value == "Unknown"
    assert claims[0].source_ids == [] or claims[0].source_ids is None
    # Second claim: valid refs [0, 1] -> two source_ids
    assert claims[1].field == "name"
    assert len(claims[1].source_ids or []) == 2
