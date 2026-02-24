"""ESL gate filter — filter suppressed entities, apply tone constraints (Issue #175, Phase 3).

Used by briefing and ORE to exclude suppressed entities and cap engagement_type
when allow_with_constraints.
"""

from __future__ import annotations

from typing import Literal

# Recommendation type order: lower index = more conservative.
# Used to cap engagement_type when tone_constraint applies.
_RECOMMENDATION_ORDER: tuple[str, ...] = (
    "Observe Only",
    "Soft Value Share",
    "Low-Pressure Intro",
    "Standard Outreach",
    "Direct Strategic Outreach",
)

ESLDecision = Literal["allow", "allow_with_constraints", "suppress"]


def get_esl_decision_from_explain(explain: dict | None) -> ESLDecision | None:
    """Extract esl_decision from engagement snapshot explain.

    Returns None when missing (legacy rows → treat as allow).
    """
    if not explain or not isinstance(explain, dict):
        return None
    raw = explain.get("esl_decision")
    if raw in ("allow", "allow_with_constraints", "suppress"):
        return raw
    return None


def is_suppressed(explain: dict | None) -> bool:
    """Return True when entity should be excluded (esl_decision == 'suppress')."""
    return get_esl_decision_from_explain(explain) == "suppress"


def is_suppressed_from_engagement(
    esl_decision: str | None,
    explain: dict | None,
) -> bool:
    """Check column first, then explain (Phase 4: prefer dedicated columns)."""
    if esl_decision == "suppress":
        return True
    return is_suppressed(explain)


def apply_tone_constraint(
    engagement_type: str,
    tone_constraint: str | None,
) -> str:
    """Cap engagement_type at tone_constraint when allow_with_constraints.

    When tone_constraint is None, returns engagement_type unchanged.
    When tone_constraint is set, returns the more conservative of the two.
    """
    if not tone_constraint or not isinstance(tone_constraint, str):
        return engagement_type
    try:
        idx_actual = _RECOMMENDATION_ORDER.index(engagement_type)
    except ValueError:
        return engagement_type
    try:
        idx_cap = _RECOMMENDATION_ORDER.index(tone_constraint)
    except ValueError:
        return engagement_type
    capped_idx = min(idx_actual, idx_cap)
    return _RECOMMENDATION_ORDER[capped_idx]


def get_effective_engagement_type(
    engagement_type: str,
    explain: dict | None,
    esl_decision: str | None = None,
) -> str:
    """Return engagement_type capped by tone_constraint when allow_with_constraints.

    Prefers esl_decision column when provided (Phase 4).
    """
    decision = esl_decision or get_esl_decision_from_explain(explain)
    if decision != "allow_with_constraints":
        return engagement_type
    if not explain or not isinstance(explain, dict):
        return engagement_type
    tone_constraint = explain.get("tone_constraint")
    return apply_tone_constraint(engagement_type, tone_constraint)
