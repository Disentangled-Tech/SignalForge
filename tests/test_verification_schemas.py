"""Unit tests for verification schemas (Issue #278, M1)."""

from __future__ import annotations

from app.verification.schemas import VerificationReasonCode, VerificationResult


def test_verification_result_passed_empty_reason_codes() -> None:
    """VerificationResult with passed=True has empty reason_codes."""
    r = VerificationResult(passed=True, reason_codes=[])
    assert r.passed is True
    assert r.reason_codes == []


def test_verification_result_failed_with_reason_codes() -> None:
    """VerificationResult with passed=False can have reason_codes."""
    codes = [
        VerificationReasonCode.EVENT_TYPE_UNKNOWN.value,
        VerificationReasonCode.FACT_DOMAIN_MISMATCH.value,
    ]
    r = VerificationResult(passed=False, reason_codes=codes)
    assert r.passed is False
    assert r.reason_codes == codes


def test_verification_reason_code_enum_values() -> None:
    """VerificationReasonCode has expected string values for quarantine payload."""
    assert VerificationReasonCode.EVENT_TYPE_UNKNOWN == "EVENT_TYPE_UNKNOWN"
    assert (
        VerificationReasonCode.EVENT_MISSING_TIMESTAMPED_CITATION
        == "EVENT_MISSING_TIMESTAMPED_CITATION"
    )
    assert VerificationReasonCode.EVENT_MISSING_REQUIRED_FIELDS == "EVENT_MISSING_REQUIRED_FIELDS"
    assert VerificationReasonCode.FACT_DOMAIN_MISMATCH == "FACT_DOMAIN_MISMATCH"
    assert (
        VerificationReasonCode.FACT_FOUNDER_MISSING_PRIMARY_SOURCE
        == "FACT_FOUNDER_MISSING_PRIMARY_SOURCE"
    )
    assert (
        VerificationReasonCode.FACT_HIRING_MISSING_JOBS_OR_ATS == "FACT_HIRING_MISSING_JOBS_OR_ATS"
    )


def test_verification_result_default_reason_codes() -> None:
    """VerificationResult defaults reason_codes to empty list."""
    r = VerificationResult(passed=True)
    assert r.reason_codes == []
