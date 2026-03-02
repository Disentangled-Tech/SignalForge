"""Unit tests for verification service (Issue #278, M1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.schemas.scout import EvidenceBundle, EvidenceItem
from app.verification import verify_bundle, verify_bundles
from app.verification.schemas import VerificationResult


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


def test_verify_bundle_returns_passed_true_when_rules_pass() -> None:
    """verify_bundle returns passed=True and empty reason_codes when all rules pass (M1 stubs)."""
    bundle = _minimal_bundle(evidence_count=1)
    result = verify_bundle(bundle, None)
    assert isinstance(result, VerificationResult)
    assert result.passed is True
    assert result.reason_codes == []


def test_verify_bundle_with_structured_payload() -> None:
    """verify_bundle accepts optional structured_payload and returns result."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {"events": [], "company": {"name": "Acme", "domain": "acme.example.com"}}
    result = verify_bundle(bundle, payload)
    assert result.passed is True
    assert result.reason_codes == []


def test_verify_bundles_returns_one_result_per_bundle() -> None:
    """verify_bundles returns list of VerificationResult in same order as bundles."""
    b1 = _minimal_bundle(name="First", evidence_count=0)
    b2 = _minimal_bundle(name="Second", website="https://second.example.com", evidence_count=1)
    results = verify_bundles([b1, b2])
    assert len(results) == 2
    assert all(isinstance(r, VerificationResult) for r in results)
    assert results[0].passed is True and results[1].passed is True


def test_verify_bundles_with_structured_payloads_aligned_by_index() -> None:
    """verify_bundles uses structured_payloads[i] for bundle i when provided."""
    b1 = _minimal_bundle(name="A", evidence_count=1)
    b2 = _minimal_bundle(name="B", evidence_count=1)
    payloads = [{"events": []}, {"events": [], "company": {"name": "B", "domain": "b.example.com"}}]
    results = verify_bundles([b1, b2], structured_payloads=payloads)
    assert len(results) == 2
    assert results[0].passed is True and results[1].passed is True


def test_verify_bundles_raises_when_payloads_length_mismatch() -> None:
    """verify_bundles raises ValueError when structured_payloads length != bundles length."""
    b1 = _minimal_bundle()
    with pytest.raises(ValueError, match="structured_payloads length must match bundles"):
        verify_bundles([b1], structured_payloads=[{}, {}])


def test_verify_bundles_empty_list_returns_empty_results() -> None:
    """verify_bundles with empty bundles returns empty list."""
    assert verify_bundles([]) == []
    assert verify_bundles([], structured_payloads=[]) == []


def test_verify_bundle_returns_passed_false_when_event_rule_fails() -> None:
    """verify_bundle returns passed=False and reason_codes when an event fails (M2)."""
    bundle = _minimal_bundle(evidence_count=1)
    payload = {"events": [{"event_type": "not_in_taxonomy", "confidence": 0.9}]}
    result = verify_bundle(bundle, payload)
    assert result.passed is False
    assert len(result.reason_codes) >= 1
    assert "EVENT_TYPE_UNKNOWN" in result.reason_codes
