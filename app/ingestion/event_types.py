"""Canonical signal event taxonomy (v2-spec §3, Issue #89).

TEST-ONLY FALLBACK (Phase 4, Plan Step 6):
Production must use pack taxonomy (pack.taxonomy.signal_ids). This module is used
only when pack is None, which occurs in tests or legacy callers. New code should
always pass a pack to normalize_raw_event.
"""

from __future__ import annotations

# All known event types from scoring constants + v2-spec §3
# Used for validating event_type_candidate when pack is None (test fallback only)
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
})


def is_valid_event_type(candidate: str) -> bool:
    """Return True if candidate is a known event type."""
    return candidate in SIGNAL_EVENT_TYPES
