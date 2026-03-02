"""Verification Gate rules (Issue #278, M1).

Pack-agnostic deterministic rules for fact and event validation. Each rule returns
a list of reason codes (empty if pass). M1: stubs only; M2/M5 implement event and
fact rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.scout import EvidenceBundle


def check_event_type_in_taxonomy(
    _bundle: EvidenceBundle,
    structured_payload: dict | None,
) -> list[str]:
    """Event rule: every core event candidate event_type must be in core taxonomy.

    M1: Stub — returns no failures. M2: use is_valid_signal_id from core_taxonomy.
    """
    return []


def check_event_timestamped_citation(
    _bundle: EvidenceBundle,
    structured_payload: dict | None,
) -> list[str]:
    """Event rule: each core event must have at least one source_ref to evidence with timestamp_seen.

    M1: Stub — returns no failures. M2: implement.
    """
    return []


def check_event_required_fields(
    _bundle: EvidenceBundle,
    structured_payload: dict | None,
) -> list[str]:
    """Event rule: event_type and confidence present; event_time optional.

    M1: Stub — returns no failures. M2: implement.
    """
    return []


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
