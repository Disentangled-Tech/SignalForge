"""Canonical signal event taxonomy (v2-spec §3, Issue #89).

Issue #285, Milestone 4: Prefer core_taxonomy for validation; SIGNAL_EVENT_TYPES
is deprecated for new code but kept for backward compatibility (e.g. incorporation
and any types not yet in core taxonomy). is_valid_event_type delegates to core
when available.
"""

from __future__ import annotations

# Deprecated: Prefer app.core_taxonomy.loader.get_core_signal_ids / is_valid_signal_id.
# Kept for backward compat (e.g. incorporation, which is ingest-only and not in core).
SIGNAL_EVENT_TYPES: frozenset[str] = frozenset({
    # Momentum
    "funding_raised",
    "job_posted_engineering",
    "job_posted_infra",
    "headcount_growth",
    "launch_major",
    # Complexity
    "api_launched",
    "ai_feature_launched",
    "enterprise_feature",
    "compliance_mentioned",
    # Pressure
    "enterprise_customer",
    "regulatory_deadline",
    "founder_urgency_language",
    "revenue_milestone",
    # Leadership Gap
    "cto_role_posted",
    "no_cto_detected",
    "fractional_request",
    "advisor_request",
    "cto_hired",  # suppressor
    # Core platform types (Issue #244, #250); packs may omit from taxonomy
    "repo_activity",
    # Core (Issue #250): Delaware incorporation provider
    "incorporation",
})


def is_valid_event_type(candidate: str) -> bool:
    """Return True if candidate is a known event type.

    Delegates to core taxonomy when available (Issue #285, Milestone 4);
    falls back to SIGNAL_EVENT_TYPES for backward compat (e.g. incorporation).
    """
    from app.core_taxonomy.loader import is_valid_signal_id

    if is_valid_signal_id(candidate):
        return True
    return candidate in SIGNAL_EVENT_TYPES
