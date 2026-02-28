"""Tests for scout (LLM Discovery) schemas — Evidence Bundles, citation requirement, JSON schema."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.scout import (
    EvidenceBundle,
    EvidenceItem,
    RunScoutRequest,
    ScoutRunInput,
    ScoutRunMetadata,
    ScoutRunResult,
    evidence_bundle_json_schema,
)

# ── EvidenceItem ────────────────────────────────────────────────────────────


def test_evidence_item_valid() -> None:
    """EvidenceItem accepts valid url, snippet, timestamp, source_type, confidence."""
    item = EvidenceItem(
        url="https://example.com/news",
        quoted_snippet="Company raised Series A.",
        timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
        source_type="news",
        confidence_score=0.9,
    )
    assert item.url == "https://example.com/news"
    assert item.quoted_snippet == "Company raised Series A."
    assert item.source_type == "news"
    assert item.confidence_score == 0.9


def test_evidence_item_confidence_bounds() -> None:
    """EvidenceItem accepts confidence 0.0 and 1.0; rejects < 0 or > 1."""
    EvidenceItem(
        url="https://x.com",
        quoted_snippet="x",
        timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
        source_type="x",
        confidence_score=0.0,
    )
    EvidenceItem(
        url="https://x.com",
        quoted_snippet="x",
        timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
        source_type="x",
        confidence_score=1.0,
    )
    with pytest.raises(ValueError):
        EvidenceItem(
            url="https://x.com",
            quoted_snippet="x",
            timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
            source_type="x",
            confidence_score=-0.1,
        )
    with pytest.raises(ValueError):
        EvidenceItem(
            url="https://x.com",
            quoted_snippet="x",
            timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
            source_type="x",
            confidence_score=1.1,
        )


def test_evidence_item_forbid_extra_fields() -> None:
    """EvidenceItem forbids extra fields (strict schema)."""
    with pytest.raises(ValueError):
        EvidenceItem(
            url="https://x.com",
            quoted_snippet="x",
            timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
            source_type="x",
            confidence_score=0.5,
            signal_id="funding_raised",  # not allowed
        )


# ── EvidenceBundle: allowed fields ───────────────────────────────────────────


def test_evidence_bundle_valid_with_evidence_and_hypothesis() -> None:
    """EvidenceBundle accepts candidate_company_name, website, why_now, evidence, missing_information."""
    bundle = EvidenceBundle(
        candidate_company_name="Acme Inc",
        company_website="https://acme.example.com",
        why_now_hypothesis="Recently raised Series A; hiring CTO.",
        evidence=[
            EvidenceItem(
                url="https://acme.example.com/news",
                quoted_snippet="Series A announced.",
                timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
                source_type="news",
                confidence_score=0.9,
            ),
        ],
        missing_information=["Exact funding amount"],
    )
    assert bundle.candidate_company_name == "Acme Inc"
    assert bundle.company_website == "https://acme.example.com"
    assert len(bundle.evidence) == 1
    assert bundle.evidence[0].url == "https://acme.example.com/news"
    assert "Series A" in bundle.why_now_hypothesis
    assert bundle.missing_information == ["Exact funding amount"]


def test_evidence_bundle_valid_empty_hypothesis_empty_evidence() -> None:
    """EvidenceBundle accepts empty why_now_hypothesis and empty evidence (no claim = no citation required)."""
    bundle = EvidenceBundle(
        candidate_company_name="Beta LLC",
        company_website="https://beta.example.com",
        why_now_hypothesis="",
        evidence=[],
        missing_information=[],
    )
    assert bundle.why_now_hypothesis == ""
    assert bundle.evidence == []


# ── EvidenceBundle: citation requirement ────────────────────────────────────


def test_evidence_bundle_rejects_non_empty_hypothesis_with_empty_evidence() -> None:
    """Bundle with non-empty why_now_hypothesis and empty evidence is rejected (citation requirement)."""
    with pytest.raises(ValueError, match="evidence must be non-empty when why_now_hypothesis"):
        EvidenceBundle(
            candidate_company_name="Acme",
            company_website="https://acme.example.com",
            why_now_hypothesis="They are scaling and need a CTO.",
            evidence=[],
            missing_information=[],
        )


def test_evidence_bundle_accepts_evidence_and_hypothesis() -> None:
    """Bundle with both evidence and why_now_hypothesis is accepted."""
    EvidenceBundle(
        candidate_company_name="Acme",
        company_website="https://acme.example.com",
        why_now_hypothesis="They are scaling.",
        evidence=[
            EvidenceItem(
                url="https://acme.example.com/jobs",
                quoted_snippet="We are hiring a CTO.",
                timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
                source_type="careers",
                confidence_score=0.85,
            ),
        ],
        missing_information=[],
    )


def test_evidence_bundle_whitespace_only_hypothesis_treated_as_empty() -> None:
    """Whitespace-only why_now_hypothesis does not require evidence (stripped)."""
    EvidenceBundle(
        candidate_company_name="Acme",
        company_website="https://acme.example.com",
        why_now_hypothesis="   \n  ",
        evidence=[],
        missing_information=[],
    )


# ── EvidenceBundle: no pack/signal fields ───────────────────────────────────


def test_evidence_bundle_forbid_extra_fields() -> None:
    """EvidenceBundle forbids pack-specific or signal fields (strict schema)."""
    with pytest.raises(ValueError):
        EvidenceBundle(
            candidate_company_name="Acme",
            company_website="https://acme.example.com",
            signal_id="cto_role_posted",  # not allowed
            evidence=[],
        )


# ── RunScoutRequest (POST /internal/run_scout body) ──────────────────────────


def test_run_scout_request_requires_icp_definition() -> None:
    """RunScoutRequest requires non-empty icp_definition."""
    RunScoutRequest(icp_definition="Seed-stage B2B", page_fetch_limit=10)
    with pytest.raises(ValidationError):
        RunScoutRequest(icp_definition="", page_fetch_limit=10)
    with pytest.raises(ValidationError):
        RunScoutRequest(icp_definition="   ", page_fetch_limit=10)


def test_run_scout_request_page_fetch_limit_bounds() -> None:
    """RunScoutRequest accepts page_fetch_limit 0 and 100; rejects < 0 or > 100."""
    RunScoutRequest(icp_definition="B2B", page_fetch_limit=0)
    RunScoutRequest(icp_definition="B2B", page_fetch_limit=100)
    RunScoutRequest(icp_definition="B2B")  # default 10
    with pytest.raises(ValidationError):
        RunScoutRequest(icp_definition="B2B", page_fetch_limit=-1)
    with pytest.raises(ValidationError):
        RunScoutRequest(icp_definition="B2B", page_fetch_limit=101)


def test_run_scout_request_optional_fields() -> None:
    """RunScoutRequest allows exclusion_rules, pack_id, workspace_id to be None; default page_fetch_limit 10."""
    req = RunScoutRequest(icp_definition="Fintech")
    assert req.exclusion_rules is None
    assert req.pack_id is None
    assert req.workspace_id is None
    assert req.page_fetch_limit == 10


def test_run_scout_request_forbid_extra() -> None:
    """RunScoutRequest forbids extra fields."""
    with pytest.raises(ValidationError):
        RunScoutRequest(
            icp_definition="B2B",
            extra_field="not allowed",
        )


# ── ScoutRunInput ───────────────────────────────────────────────────────────


def test_scout_run_input_valid() -> None:
    """ScoutRunInput accepts icp_definition, optional exclusion_rules and pack_id."""
    inp = ScoutRunInput(
        icp_definition="Seed-stage B2B SaaS in fintech",
        exclusion_rules="Exclude regulated banking",
        pack_id="fractional_cto_v1",
    )
    assert inp.icp_definition == "Seed-stage B2B SaaS in fintech"
    assert inp.exclusion_rules == "Exclude regulated banking"
    assert inp.pack_id == "fractional_cto_v1"


def test_scout_run_input_optional_fields() -> None:
    """ScoutRunInput allows exclusion_rules and pack_id to be None."""
    inp = ScoutRunInput(icp_definition="Any startup with technical hiring needs")
    assert inp.exclusion_rules is None
    assert inp.pack_id is None


def test_scout_run_input_forbid_extra() -> None:
    """ScoutRunInput forbids extra fields."""
    with pytest.raises(ValueError):
        ScoutRunInput(
            icp_definition="Fintech",
            page_fetch_limit=100,  # not in schema
        )


# ── ScoutRunResult / ScoutRunMetadata ────────────────────────────────────────


def test_scout_run_result_valid() -> None:
    """ScoutRunResult accepts run_id, bundles, metadata."""
    result = ScoutRunResult(
        run_id="run-abc-123",
        bundles=[
            EvidenceBundle(
                candidate_company_name="Acme",
                company_website="https://acme.example.com",
                why_now_hypothesis="",
                evidence=[],
            ),
        ],
        metadata=ScoutRunMetadata(
            model_version="gpt-4o",
            tokens_used=500,
            latency_ms=1200,
            page_fetch_count=10,
        ),
    )
    assert result.run_id == "run-abc-123"
    assert len(result.bundles) == 1
    assert result.metadata.model_version == "gpt-4o"
    assert result.metadata.tokens_used == 500


# ── JSON schema export ──────────────────────────────────────────────────────


def test_evidence_bundle_json_schema_export() -> None:
    """evidence_bundle_json_schema returns a dict with expected top-level keys."""
    schema = evidence_bundle_json_schema()
    assert isinstance(schema, dict)
    assert "$defs" in schema or "properties" in schema
    props = schema.get("properties", schema)
    if "properties" in schema:
        props = schema["properties"]
    assert "candidate_company_name" in props
    assert "company_website" in props
    assert "why_now_hypothesis" in props
    assert "evidence" in props
    assert "missing_information" in props
    # No pack/signal fields in schema
    assert "signal_id" not in props
    assert "event_type" not in props
