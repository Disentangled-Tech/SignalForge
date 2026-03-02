"""Unit tests for verification rules (Issue #278, M1). Rules are stubs; each returns []."""

from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.scout import EvidenceBundle, EvidenceItem
from app.verification.rules import (
    check_event_required_fields,
    check_event_timestamped_citation,
    check_event_type_in_taxonomy,
    check_fact_domain_match,
    check_fact_founder_primary_source,
    check_fact_hiring_jobs_or_ats,
    run_all_rules,
)


def _make_item(url: str, snippet: str, source_type: str = "web") -> EvidenceItem:
    return EvidenceItem(
        url=url,
        quoted_snippet=snippet,
        timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
        source_type=source_type,
        confidence_score=0.9,
    )


def _minimal_bundle(
    name: str = "Acme",
    website: str = "https://acme.example.com",
    evidence_count: int = 0,
) -> EvidenceBundle:
    evidence = [_make_item("https://example.com/p1", "snippet one")] if evidence_count else []
    return EvidenceBundle(
        candidate_company_name=name,
        company_website=website,
        why_now_hypothesis="Hypothesis." if evidence else "",
        evidence=evidence,
        missing_information=[],
    )


def test_check_event_type_in_taxonomy_stub_returns_empty() -> None:
    """M1 stub: check_event_type_in_taxonomy returns no reason codes."""
    bundle = _minimal_bundle()
    assert check_event_type_in_taxonomy(bundle, None) == []
    assert check_event_type_in_taxonomy(bundle, {"events": []}) == []


def test_check_event_timestamped_citation_stub_returns_empty() -> None:
    """M1 stub: check_event_timestamped_citation returns no reason codes."""
    bundle = _minimal_bundle(evidence_count=1)
    assert check_event_timestamped_citation(bundle, None) == []
    assert check_event_timestamped_citation(bundle, {"events": []}) == []


def test_check_event_required_fields_stub_returns_empty() -> None:
    """M1 stub: check_event_required_fields returns no reason codes."""
    bundle = _minimal_bundle()
    assert check_event_required_fields(bundle, None) == []
    assert (
        check_event_required_fields(
            bundle, {"events": [{"event_type": "funding_raised", "confidence": 0.9}]}
        )
        == []
    )


def test_check_fact_domain_match_stub_returns_empty() -> None:
    """M1 stub: check_fact_domain_match returns no reason codes."""
    bundle = _minimal_bundle()
    assert check_fact_domain_match(bundle, None) == []
    assert check_fact_domain_match(bundle, {}) == []


def test_check_fact_founder_primary_source_stub_returns_empty() -> None:
    """M1 stub: check_fact_founder_primary_source returns no reason codes."""
    bundle = _minimal_bundle()
    assert check_fact_founder_primary_source(bundle, None) == []
    assert check_fact_founder_primary_source(bundle, {"persons": []}) == []


def test_check_fact_hiring_jobs_or_ats_stub_returns_empty() -> None:
    """M1 stub: check_fact_hiring_jobs_or_ats returns no reason codes."""
    bundle = _minimal_bundle()
    assert check_fact_hiring_jobs_or_ats(bundle, None) == []
    assert check_fact_hiring_jobs_or_ats(bundle, {"events": []}) == []


def test_run_all_rules_returns_empty_when_all_stubs_pass() -> None:
    """run_all_rules returns empty list when every rule stub passes."""
    bundle = _minimal_bundle(evidence_count=1)
    assert run_all_rules(bundle, None) == []
    assert (
        run_all_rules(
            bundle, {"events": [], "company": {"name": "Acme", "domain": "acme.example.com"}}
        )
        == []
    )
