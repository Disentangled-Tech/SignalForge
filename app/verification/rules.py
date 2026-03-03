"""Verification Gate rules (Issue #278, M1).

Pack-agnostic deterministic rules for fact and event validation. Each rule returns
a list of reason codes (empty if pass). M1: stubs only; M2 event rules; M5 fact rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.core_taxonomy.loader import is_valid_signal_id
from app.schemas.core_events import get_events_from_payload
from app.verification.schemas import VerificationReasonCode

if TYPE_CHECKING:
    from app.schemas.scout import EvidenceBundle

# Hiring-related signal_ids from core taxonomy (M5: jobs/ATS evidence required when present).
# TODO(#278): derive or validate against taxonomy (e.g. tag in taxonomy or shared constant) so new hiring signal_ids stay in sync.
_HIRING_SIGNAL_IDS = frozenset(
    {
        "job_posted_engineering",
        "job_posted_infra",
        "cto_role_posted",
        "cto_hired",
    }
)


def _normalize_domain(url: str) -> str | None:
    """Extract domain from URL: lowercase, strip www, strip port. Returns None if invalid.

    TODO(#278): align with company_resolver.extract_domain (strip only :80/:443) for strict consistency.
    """
    if not url or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
        if not parsed.netloc:
            return None
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if ":" in host:
            host, _ = host.rsplit(":", 1)
        return host if host else None
    except Exception:  # TODO(#278): catch specific exceptions (e.g. ValueError) or re-raise to avoid swallowing logic bugs
        return None


def _get_events(structured_payload: dict | None) -> list[dict[str, Any]]:
    """Return list of event dicts from structured_payload.

    Accepts both 'events' and 'core_event_candidates' (ExtractionResult shape).
    Prefers 'events' when both keys present. Empty if missing or not a list.
    """
    return get_events_from_payload(structured_payload)


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
    bundle: EvidenceBundle,
    _structured_payload: dict | None,
) -> list[str]:
    """Fact rule: company_website domain must match at least one evidence URL host.

    M5: When evidence is non-empty, at least one evidence item URL host must match
    the company_website domain (normalized). No evidence → pass (nothing to match).
    """
    if not bundle.evidence:
        return []
    company_domain = _normalize_domain(bundle.company_website)
    if not company_domain:
        return [VerificationReasonCode.FACT_DOMAIN_MISMATCH]
    for item in bundle.evidence:
        evidence_domain = _normalize_domain(item.url)
        if evidence_domain and evidence_domain == company_domain:
            return []
    return [VerificationReasonCode.FACT_DOMAIN_MISMATCH]


def _get_persons(structured_payload: dict | None) -> list[dict[str, Any]]:
    """Return list of person/founder dicts from structured_payload; empty if missing."""
    if not structured_payload:
        return []
    # Support both "persons" (list) and "person" (single dict, extractor output)
    persons = structured_payload.get("persons")
    if isinstance(persons, list):
        return [p for p in persons if isinstance(p, dict)]
    person = structured_payload.get("person")
    if isinstance(person, dict):
        return [person]
    return []


def _get_claims(structured_payload: dict | None) -> list[dict[str, Any]]:
    """Return list of claim dicts from structured_payload; empty if missing."""
    if not structured_payload or not isinstance(structured_payload.get("claims"), list):
        return []
    return [c for c in structured_payload["claims"] if isinstance(c, dict)]


def check_fact_founder_primary_source(
    bundle: EvidenceBundle,
    structured_payload: dict | None,
) -> list[str]:
    """Fact rule: if structured_payload has founder/person, require ≥1 primary source.

    M5: When persons (or person) is non-empty, at least one claim with entity_type
    person/founder must have non-empty source_refs pointing into bundle.evidence.
    """
    persons = _get_persons(structured_payload)
    if not persons:
        return []
    evidence_len = len(bundle.evidence)
    for claim in _get_claims(structured_payload):
        entity_type = (claim.get("entity_type") or "").strip().lower()
        if entity_type not in ("person", "founder"):
            continue
        refs = claim.get("source_refs")
        if not isinstance(refs, list) or not refs:
            continue
        if any(isinstance(i, int) and 0 <= i < evidence_len for i in refs):
            return []
    return [VerificationReasonCode.FACT_FOUNDER_MISSING_PRIMARY_SOURCE]


def _is_jobs_or_ats_url(url: str) -> bool:
    """True if URL looks like a jobs/careers page or ATS (path or domain heuristic)."""
    if not url or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip().lower())
        path = (parsed.path or "").strip("/")
        netloc = parsed.netloc or ""
        jobs_path_segments = ("jobs", "careers", "openings", "positions", "vacancies", "join")
        if any(seg in path for seg in jobs_path_segments):
            return True
        ats_domains = ("greenhouse.io", "lever.co", "workable.com", "bamboohr.com", "ashbyhq.com")
        if any(ats in netloc for ats in ats_domains):
            return True
        if "jobs." in netloc or ".jobs" in netloc:
            return True
        return False
    except (
        Exception
    ):  # TODO(#278): catch specific exceptions or re-raise to avoid swallowing logic bugs
        return False


def check_fact_hiring_jobs_or_ats(
    bundle: EvidenceBundle,
    structured_payload: dict | None,
) -> list[str]:
    """Fact rule: hiring-related event types require jobs page or ATS evidence URL.

    M5: When any event_type is hiring-related (job_posted_*, cto_role_posted, cto_hired),
    at least one evidence item URL must look like jobs/careers or ATS (path/domain heuristic).
    """
    events = _get_events(structured_payload)
    has_hiring_event = any(
        (e.get("event_type") or "").strip() in _HIRING_SIGNAL_IDS for e in events
    )
    if not has_hiring_event:
        return []
    if not bundle.evidence:
        return [VerificationReasonCode.FACT_HIRING_MISSING_JOBS_OR_ATS]
    for item in bundle.evidence:
        if _is_jobs_or_ats_url(item.url):
            return []
    return [VerificationReasonCode.FACT_HIRING_MISSING_JOBS_OR_ATS]


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
