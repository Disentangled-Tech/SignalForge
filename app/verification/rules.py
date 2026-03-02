"""Verification Gate rules (Issue #278, M1).

Pack-agnostic deterministic rules for fact and event validation. Each rule returns
a list of reason codes (empty if pass). M1: stubs only; M2/M5 implement event and
fact rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core_taxonomy.loader import is_valid_signal_id
from app.verification.schemas import VerificationReasonCode

if TYPE_CHECKING:
    from app.schemas.scout import EvidenceBundle


def _get_events(structured_payload: dict | None) -> list[dict[str, Any]]:
    """Return list of event dicts from structured_payload; empty if missing or not a list."""
    if not structured_payload or not isinstance(structured_payload.get("events"), list):
        return []
    return [e for e in structured_payload["events"] if isinstance(e, dict)]


def check_event_type_in_taxonomy(
    _bundle: EvidenceBundle,
    structured_payload: dict | None,
) -> list[str]:
    """Event rule: every core event candidate event_type must be in core taxonomy.

    M2: uses is_valid_signal_id from core_taxonomy. Returns EVENT_TYPE_UNKNOWN if any
    event has unknown event_type.
    """
    reason_codes: list[str] = []
    for event in _get_events(structured_payload):
        event_type = event.get("event_type")
        if event_type is None or not isinstance(event_type, str):
            reason_codes.append(VerificationReasonCode.EVENT_TYPE_UNKNOWN)
            break
        if not is_valid_signal_id(event_type.strip()):
            reason_codes.append(VerificationReasonCode.EVENT_TYPE_UNKNOWN)
            break
    return reason_codes


def check_event_timestamped_citation(
    bundle: EvidenceBundle,
    structured_payload: dict | None,
) -> list[str]:
    """Event rule: each core event must have at least one source_ref to evidence with timestamp_seen.

    M2: requires at least one source_ref pointing to a valid evidence index (evidence
    items have required timestamp_seen). Returns EVENT_MISSING_TIMESTAMPED_CITATION
    if any event lacks a valid timestamped citation.
    """
    reason_codes: list[str] = []
    evidence = bundle.evidence
    evidence_len = len(evidence)
    for event in _get_events(structured_payload):
        source_refs = event.get("source_refs")
        if not isinstance(source_refs, list):
            reason_codes.append(VerificationReasonCode.EVENT_MISSING_TIMESTAMPED_CITATION)
            break
        has_valid_ref = any(isinstance(i, int) and 0 <= i < evidence_len for i in source_refs)
        if not has_valid_ref:
            reason_codes.append(VerificationReasonCode.EVENT_MISSING_TIMESTAMPED_CITATION)
            break
    return reason_codes


def check_event_required_fields(
    _bundle: EvidenceBundle,
    structured_payload: dict | None,
) -> list[str]:
    """Event rule: event_type and confidence present; event_time optional.

    M2: requires event_type (non-empty string) and confidence (present) per
    CoreEventCandidate. Returns EVENT_MISSING_REQUIRED_FIELDS if any event fails.
    """
    reason_codes: list[str] = []
    for event in _get_events(structured_payload):
        event_type = event.get("event_type")
        confidence = event.get("confidence")
        has_event_type = (
            event_type is not None and isinstance(event_type, str) and event_type.strip() != ""
        )
        # Reject bool (subclass of int); require numeric only per CoreEventCandidate
        has_confidence = (
            confidence is not None
            and not isinstance(confidence, bool)
            and isinstance(confidence, (int, float))
        )  # 0.0 is valid
        if not has_event_type or not has_confidence:
            reason_codes.append(VerificationReasonCode.EVENT_MISSING_REQUIRED_FIELDS)
            break
    return reason_codes


def check_fact_domain_match(
    _bundle: EvidenceBundle,
    _structured_payload: dict | None,
) -> list[str]:
    """Fact rule: company_website domain must match at least one evidence URL host.

    M1: Stub — returns no failures. M5: implement.
    """
    return []


def check_fact_founder_primary_source(
    _bundle: EvidenceBundle,
    structured_payload: dict | None,
) -> list[str]:
    """Fact rule: if structured_payload has founder/person, require ≥1 primary source.

    M1: Stub — returns no failures. M5: implement.
    """
    return []


def check_fact_hiring_jobs_or_ats(
    _bundle: EvidenceBundle,
    structured_payload: dict | None,
) -> list[str]:
    """Fact rule: hiring-related event types require jobs page or ATS evidence URL.

    M1: Stub — returns no failures. M5: implement.
    """
    return []


def run_all_rules(bundle: EvidenceBundle, structured_payload: dict | None) -> list[str]:
    """Run all verification rules; return combined list of reason codes (empty if pass)."""
    reason_codes: list[str] = []
    rules = [
        check_event_type_in_taxonomy,
        check_event_timestamped_citation,
        check_event_required_fields,
        check_fact_domain_match,
        check_fact_founder_primary_source,
        check_fact_hiring_jobs_or_ats,
    ]
    for rule in rules:
        codes = rule(bundle, structured_payload)
        for code in codes:
            if code not in reason_codes:
                reason_codes.append(code)
    return reason_codes
