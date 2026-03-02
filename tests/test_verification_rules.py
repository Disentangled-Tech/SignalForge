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


def test_run_all_rules_returns_empty_when_all_pass() -> None:
    """run_all_rules returns empty list when every rule passes (no events or valid events)."""
    bundle = _minimal_bundle(evidence_count=1)
    assert run_all_rules(bundle, None) == []
    assert (
        run_all_rules(
            bundle, {"events": [], "company": {"name": "Acme", "domain": "acme.example.com"}}
        )
        == []
    )


def test_run_all_rules_returns_reason_codes_when_event_fails() -> None:
    """run_all_rules returns combined reason codes when an event rule fails (M2)."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {"events": [{"event_type": "invalid_signal", "confidence": 0.9}]}
    codes = run_all_rules(bundle, payload)
    assert VerificationReasonCode.EVENT_TYPE_UNKNOWN in codes


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
