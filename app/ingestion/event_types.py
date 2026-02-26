"""Canonical signal event taxonomy (v2-spec §3, Issue #89)."""

from __future__ import annotations

# All known event types from scoring constants + v2-spec §3
# Used for validating event_type_candidate during normalization
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
    # Core (Issue #244): GitHub provider
    "repo_activity",
    # Core (Issue #250): Delaware incorporation provider
    "incorporation",
})


def is_valid_event_type(candidate: str) -> bool:
    """Return True if candidate is a known event type."""
    return candidate in SIGNAL_EVENT_TYPES
