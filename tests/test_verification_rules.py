"""Unit tests for verification rules (Issue #278, M1/M2). M1 stubs for fact rules; M2 event rules implemented."""

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
from app.verification.schemas import VerificationReasonCode


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


def test_check_event_type_in_taxonomy_returns_empty_when_no_events() -> None:
    """check_event_type_in_taxonomy returns no reason codes when payload has no events."""
    bundle = _minimal_bundle()
    assert check_event_type_in_taxonomy(bundle, None) == []
    assert check_event_type_in_taxonomy(bundle, {"events": []}) == []


def test_check_event_type_in_taxonomy_returns_empty_for_valid_signal_id() -> None:
    """check_event_type_in_taxonomy returns [] when event_type is in core taxonomy (M2)."""
    bundle = _minimal_bundle()
    payload = {"events": [{"event_type": "funding_raised", "confidence": 0.9}]}
    assert check_event_type_in_taxonomy(bundle, payload) == []


def test_check_event_type_in_taxonomy_returns_unknown_for_invalid_signal_id() -> None:
    """check_event_type_in_taxonomy returns EVENT_TYPE_UNKNOWN when event_type not in taxonomy (M2)."""
    bundle = _minimal_bundle()
    payload = {"events": [{"event_type": "not_in_taxonomy", "confidence": 0.9}]}
    assert check_event_type_in_taxonomy(bundle, payload) == [
        VerificationReasonCode.EVENT_TYPE_UNKNOWN
    ]


def test_check_event_type_in_taxonomy_returns_unknown_when_event_type_missing() -> None:
    """check_event_type_in_taxonomy returns EVENT_TYPE_UNKNOWN when event_type missing (M2)."""
    bundle = _minimal_bundle()
    payload = {"events": [{"confidence": 0.9}]}
    assert check_event_type_in_taxonomy(bundle, payload) == [
        VerificationReasonCode.EVENT_TYPE_UNKNOWN
    ]


def test_check_event_type_in_taxonomy_returns_unknown_when_event_type_empty_string() -> None:
    """check_event_type_in_taxonomy returns EVENT_TYPE_UNKNOWN when event_type is empty (M2)."""
    bundle = _minimal_bundle()
    payload = {"events": [{"event_type": "  ", "confidence": 0.9}]}
    assert check_event_type_in_taxonomy(bundle, payload) == [
        VerificationReasonCode.EVENT_TYPE_UNKNOWN
    ]


def test_check_event_timestamped_citation_returns_empty_when_no_events() -> None:
    """check_event_timestamped_citation returns no reason codes when payload has no events."""
    bundle = _minimal_bundle(evidence_count=1)
    assert check_event_timestamped_citation(bundle, None) == []
    assert check_event_timestamped_citation(bundle, {"events": []}) == []


def test_check_event_timestamped_citation_returns_empty_when_valid_ref() -> None:
    """check_event_timestamped_citation returns [] when event has source_ref to evidence (M2)."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {"events": [{"event_type": "funding_raised", "confidence": 0.9, "source_refs": [0]}]}
    assert check_event_timestamped_citation(bundle, payload) == []


def test_check_event_timestamped_citation_returns_code_when_no_source_refs() -> None:
    """check_event_timestamped_citation returns EVENT_MISSING_TIMESTAMPED_CITATION when no source_refs (M2)."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {"events": [{"event_type": "funding_raised", "confidence": 0.9, "source_refs": []}]}
    assert check_event_timestamped_citation(bundle, payload) == [
        VerificationReasonCode.EVENT_MISSING_TIMESTAMPED_CITATION
    ]


def test_check_event_timestamped_citation_returns_code_when_ref_out_of_range() -> None:
    """check_event_timestamped_citation returns EVENT_MISSING_TIMESTAMPED_CITATION when source_ref out of range (M2)."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {"events": [{"event_type": "funding_raised", "confidence": 0.9, "source_refs": [1]}]}
    assert check_event_timestamped_citation(bundle, payload) == [
        VerificationReasonCode.EVENT_MISSING_TIMESTAMPED_CITATION
    ]


def test_check_event_timestamped_citation_returns_code_when_source_refs_not_list() -> None:
    """check_event_timestamped_citation returns EVENT_MISSING_TIMESTAMPED_CITATION when source_refs not a list (M2)."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {"events": [{"event_type": "funding_raised", "confidence": 0.9, "source_refs": "0"}]}
    assert check_event_timestamped_citation(bundle, payload) == [
        VerificationReasonCode.EVENT_MISSING_TIMESTAMPED_CITATION
    ]


def test_check_event_required_fields_returns_empty_when_no_events() -> None:
    """check_event_required_fields returns no reason codes when payload has no events."""
    bundle = _minimal_bundle()
    assert check_event_required_fields(bundle, None) == []
    assert check_event_required_fields(bundle, {"events": []}) == []


def test_check_event_required_fields_returns_empty_when_present() -> None:
    """check_event_required_fields returns [] when event_type and confidence present (M2)."""
    bundle = _minimal_bundle()
    assert (
        check_event_required_fields(
            bundle, {"events": [{"event_type": "funding_raised", "confidence": 0.9}]}
        )
        == []
    )
    assert (
        check_event_required_fields(
            bundle, {"events": [{"event_type": "cto_role_posted", "confidence": 0.0}]}
        )
        == []
    )


def test_check_event_required_fields_returns_code_when_missing_event_type() -> None:
    """check_event_required_fields returns EVENT_MISSING_REQUIRED_FIELDS when event_type missing (M2)."""
    bundle = _minimal_bundle()
    payload = {"events": [{"confidence": 0.9}]}
    assert check_event_required_fields(bundle, payload) == [
        VerificationReasonCode.EVENT_MISSING_REQUIRED_FIELDS
    ]


def test_check_event_required_fields_returns_code_when_missing_confidence() -> None:
    """check_event_required_fields returns EVENT_MISSING_REQUIRED_FIELDS when confidence missing (M2)."""
    bundle = _minimal_bundle()
    payload = {"events": [{"event_type": "funding_raised"}]}
    assert check_event_required_fields(bundle, payload) == [
        VerificationReasonCode.EVENT_MISSING_REQUIRED_FIELDS
    ]


def test_check_event_required_fields_returns_code_when_event_type_empty() -> None:
    """check_event_required_fields returns EVENT_MISSING_REQUIRED_FIELDS when event_type empty (M2)."""
    bundle = _minimal_bundle()
    payload = {"events": [{"event_type": "", "confidence": 0.9}]}
    assert check_event_required_fields(bundle, payload) == [
        VerificationReasonCode.EVENT_MISSING_REQUIRED_FIELDS
    ]


def test_check_event_required_fields_returns_code_when_confidence_is_bool() -> None:
    """check_event_required_fields rejects bool for confidence (align with CoreEventCandidate float)."""
    bundle = _minimal_bundle()
    payload = {"events": [{"event_type": "funding_raised", "confidence": True}]}
    assert check_event_required_fields(bundle, payload) == [
        VerificationReasonCode.EVENT_MISSING_REQUIRED_FIELDS
    ]


def test_check_fact_domain_match_returns_empty_when_no_evidence() -> None:
    """M5: check_fact_domain_match returns [] when evidence is empty (nothing to match)."""
    bundle = _minimal_bundle()
    assert check_fact_domain_match(bundle, None) == []
    assert check_fact_domain_match(bundle, {}) == []


def test_check_fact_domain_match_returns_empty_when_evidence_url_matches_company_domain() -> None:
    """M5: check_fact_domain_match returns [] when at least one evidence URL host matches company_website."""
    bundle = _minimal_bundle(
        website="https://acme.example.com",
        evidence_count=1,
    )
    # Override evidence so URL is same domain as company_website
    bundle = EvidenceBundle(
        candidate_company_name=bundle.candidate_company_name,
        company_website="https://acme.example.com",
        why_now_hypothesis=bundle.why_now_hypothesis,
        evidence=[
            _make_item("https://acme.example.com/about", "snippet"),
        ],
        missing_information=bundle.missing_information,
    )
    assert check_fact_domain_match(bundle, None) == []


def test_check_fact_domain_match_returns_code_when_no_evidence_url_matches() -> None:
    """M5: check_fact_domain_match returns FACT_DOMAIN_MISMATCH when no evidence URL matches company domain."""
    bundle = _minimal_bundle(
        website="https://acme.example.com",
        evidence_count=1,
    )
    # _minimal_bundle(evidence_count=1) uses https://example.com/p1, domain example.com != acme.example.com
    assert check_fact_domain_match(bundle, None) == [VerificationReasonCode.FACT_DOMAIN_MISMATCH]


def test_check_fact_domain_match_normalizes_www() -> None:
    """M5: domain match normalizes www so www.acme.com matches acme.com."""
    bundle = EvidenceBundle(
        candidate_company_name="Acme",
        company_website="https://www.acme.com",
        why_now_hypothesis="Hypothesis.",
        evidence=[_make_item("https://acme.com/careers", "snippet")],
        missing_information=[],
    )
    assert check_fact_domain_match(bundle, None) == []


def test_check_fact_founder_primary_source_returns_empty_when_no_persons() -> None:
    """M5: check_fact_founder_primary_source returns [] when no persons in payload."""
    bundle = _minimal_bundle(evidence_count=1)
    assert check_fact_founder_primary_source(bundle, None) == []
    assert check_fact_founder_primary_source(bundle, {"persons": []}) == []


def test_check_fact_founder_primary_source_returns_empty_when_person_has_backing_claim() -> None:
    """M5: check_fact_founder_primary_source returns [] when a person claim has source_refs."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {
        "persons": [{"name": "Jane", "role": "CEO"}],
        "claims": [
            {"entity_type": "person", "field": "name", "value": "Jane", "source_refs": [0]},
        ],
    }
    assert check_fact_founder_primary_source(bundle, payload) == []


def test_check_fact_founder_primary_source_returns_code_when_person_without_backing_claim() -> None:
    """M5: check_fact_founder_primary_source returns FACT_FOUNDER_MISSING_PRIMARY_SOURCE when persons present but no claim with source_refs."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {
        "persons": [{"name": "Jane", "role": "CEO"}],
        "claims": [],
    }
    assert check_fact_founder_primary_source(bundle, payload) == [
        VerificationReasonCode.FACT_FOUNDER_MISSING_PRIMARY_SOURCE
    ]


def test_check_fact_founder_primary_source_accepts_founder_entity_type() -> None:
    """M5: entity_type 'founder' with source_refs passes."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {
        "persons": [{"name": "Jane"}],
        "claims": [
            {"entity_type": "founder", "field": "name", "value": "Jane", "source_refs": [0]}
        ],
    }
    assert check_fact_founder_primary_source(bundle, payload) == []


def test_check_fact_founder_primary_source_accepts_person_singleton_key() -> None:
    """M5: payload with 'person' (singular) dict is treated as one person."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {
        "person": {"name": "Jane", "role": "CEO"},
        "claims": [{"entity_type": "person", "field": "name", "value": "Jane", "source_refs": [0]}],
    }
    assert check_fact_founder_primary_source(bundle, payload) == []


def test_check_fact_hiring_jobs_or_ats_returns_empty_when_no_hiring_events() -> None:
    """M5: check_fact_hiring_jobs_or_ats returns [] when no hiring-related event types."""
    bundle = _minimal_bundle(evidence_count=1)
    assert check_fact_hiring_jobs_or_ats(bundle, None) == []
    assert check_fact_hiring_jobs_or_ats(bundle, {"events": []}) == []
    payload = {"events": [{"event_type": "funding_raised", "confidence": 0.9}]}
    assert check_fact_hiring_jobs_or_ats(bundle, payload) == []


def test_check_fact_hiring_jobs_or_ats_returns_empty_when_jobs_url_present() -> None:
    """M5: check_fact_hiring_jobs_or_ats returns [] when evidence includes jobs/careers URL."""
    bundle = _minimal_bundle(website="https://acme.example.com", evidence_count=1)
    bundle = EvidenceBundle(
        candidate_company_name=bundle.candidate_company_name,
        company_website=bundle.company_website,
        why_now_hypothesis=bundle.why_now_hypothesis,
        evidence=[_make_item("https://acme.example.com/careers", "snippet")],
        missing_information=bundle.missing_information,
    )
    payload = {"events": [{"event_type": "job_posted_engineering", "confidence": 0.9}]}
    assert check_fact_hiring_jobs_or_ats(bundle, payload) == []


def test_check_fact_hiring_jobs_or_ats_returns_code_when_hiring_event_without_jobs_url() -> None:
    """M5: check_fact_hiring_jobs_or_ats returns FACT_HIRING_MISSING_JOBS_OR_ATS when hiring event but no jobs/ATS evidence URL."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {"events": [{"event_type": "job_posted_engineering", "confidence": 0.9}]}
    assert check_fact_hiring_jobs_or_ats(bundle, payload) == [
        VerificationReasonCode.FACT_HIRING_MISSING_JOBS_OR_ATS
    ]


def test_check_fact_hiring_jobs_or_ats_accepts_ats_domain() -> None:
    """M5: evidence URL from known ATS domain (e.g. greenhouse) passes."""
    bundle = EvidenceBundle(
        candidate_company_name="Acme",
        company_website="https://acme.example.com",
        why_now_hypothesis="Hypothesis.",
        evidence=[_make_item("https://boards.greenhouse.io/acme/jobs/123", "snippet")],
        missing_information=[],
    )
    payload = {"events": [{"event_type": "cto_hired", "confidence": 0.9}]}
    assert check_fact_hiring_jobs_or_ats(bundle, payload) == []


def test_run_all_rules_returns_empty_when_all_pass() -> None:
    """run_all_rules returns empty list when every rule passes (no events or valid events)."""
    # Use same domain for company_website and evidence so fact domain rule passes (M5)
    bundle = EvidenceBundle(
        candidate_company_name="Acme",
        company_website="https://acme.example.com",
        why_now_hypothesis="Hypothesis.",
        evidence=[_make_item("https://acme.example.com/page", "snippet")],
        missing_information=[],
    )
    assert run_all_rules(bundle, None) == []
    assert (
        run_all_rules(
            bundle, {"events": [], "company": {"name": "Acme", "domain": "acme.example.com"}}
        )
        == []
    )


def test_run_all_rules_returns_reason_codes_when_event_fails() -> None:
    """run_all_rules returns combined reason codes when an event rule fails (M2)."""
    bundle = EvidenceBundle(
        candidate_company_name="Acme",
        company_website="https://acme.example.com",
        why_now_hypothesis="Hypothesis.",
        evidence=[_make_item("https://acme.example.com/p", "snippet")],
        missing_information=[],
    )
    payload = {"events": [{"event_type": "invalid_signal", "confidence": 0.9}]}
    codes = run_all_rules(bundle, payload)
    assert VerificationReasonCode.EVENT_TYPE_UNKNOWN in codes


def test_run_all_rules_returns_fact_reason_codes_when_fact_rule_fails() -> None:
    """run_all_rules returns fact reason codes when a fact rule fails (M5)."""
    # Domain mismatch: evidence URL different domain than company_website
    bundle = _minimal_bundle(website="https://acme.example.com", evidence_count=1)
    codes = run_all_rules(bundle, None)
    assert VerificationReasonCode.FACT_DOMAIN_MISMATCH in codes


def test_check_event_rules_skip_non_dict_entries_in_events() -> None:
    """_get_events skips non-dict entries; only dict items are validated (no break, documented)."""
    bundle = _minimal_bundle(evidence_count=1)
    # One valid dict + non-dict entries: only the dict is processed, so event rules pass for it
    payload = {
        "events": [
            {"event_type": "funding_raised", "confidence": 0.9, "source_refs": [0]},
            "not a dict",
            123,
            None,
        ]
    }
    assert check_event_type_in_taxonomy(bundle, payload) == []
    assert check_event_timestamped_citation(bundle, payload) == []
    assert check_event_required_fields(bundle, payload) == []
    # Only non-dict entries: no events to validate, all rules pass
    payload_no_dicts = {"events": ["skip", 0, None]}
    assert check_event_type_in_taxonomy(bundle, payload_no_dicts) == []
    assert check_event_required_fields(bundle, payload_no_dicts) == []
