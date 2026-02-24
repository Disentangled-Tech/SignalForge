"""ESL decision gate — allow/allow_with_constraints/suppress (Issue #175).

Evaluates signals + pack policy → ESL decision. Core hard bans enforced first;
pack policy (blocked_signals, prohibited_combinations, downgrade_rules,
sensitivity_mapping) applied after. Legacy pack=None → allow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.packs.loader import Pack


ESLDecision = Literal["allow", "allow_with_constraints", "suppress"]

# Signal IDs that always trigger suppress (core ethical bans). Cannot be overridden by pack.
# Empty for now; extend when domain-specific core-ban signals are defined (e.g. distress).
CORE_BAN_SIGNAL_IDS: frozenset[str] = frozenset()


@dataclass
class ESLDecisionResult:
    """Result of ESL decision evaluation (Issue #175)."""

    decision: ESLDecision
    reason_code: str
    sensitivity_level: str | None
    tone_constraint: str | None  # e.g. "Soft Value Share" max when allow_with_constraints


def evaluate_esl_decision(
    signal_ids: set[str],
    pack: Pack | None,
    company_context: dict | None = None,
) -> ESLDecisionResult:
    """Evaluate ESL gate: blocked signals, prohibited combinations, sensitivity.

    Core hard bans enforced first (cannot be overridden). Pack policy applied
    when pack is provided. pack=None → allow with reason "legacy".

    Args:
        signal_ids: Set of signal_ids present for the entity.
        pack: Loaded pack config (or None for legacy path).
        company_context: Optional company context (reserved for future use).

    Returns:
        ESLDecisionResult with decision, reason_code, sensitivity_level, tone_constraint.
    """
    del company_context  # Reserved for future use
    if pack is None:
        return ESLDecisionResult(
            decision="allow",
            reason_code="legacy",
            sensitivity_level=None,
            tone_constraint=None,
        )

    policy = pack.esl_policy or {}

    # 1. Core hard bans (cannot be overridden)
    if CORE_BAN_SIGNAL_IDS and (signal_ids & CORE_BAN_SIGNAL_IDS):
        return ESLDecisionResult(
            decision="suppress",
            reason_code="core_ban",
            sensitivity_level=None,
            tone_constraint=None,
        )

    # 2. Pack blocked_signals
    blocked = policy.get("blocked_signals") or []
    if isinstance(blocked, list):
        blocked_set = frozenset(str(s) for s in blocked)
        if signal_ids & blocked_set:
            return ESLDecisionResult(
                decision="suppress",
                reason_code="blocked_signal",
                sensitivity_level=None,
                tone_constraint=None,
            )

    # 3. Pack prohibited_combinations
    prohibited = policy.get("prohibited_combinations") or []
    if isinstance(prohibited, list):
        for pair in prohibited:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            a, b = str(pair[0]), str(pair[1])
            if {a, b} <= signal_ids:
                return ESLDecisionResult(
                    decision="suppress",
                    reason_code="prohibited_combination",
                    sensitivity_level=None,
                    tone_constraint=None,
                )

    # 4. Pack downgrade_rules → allow_with_constraints
    downgrade = policy.get("downgrade_rules") or []
    tone_constraint: str | None = None
    if isinstance(downgrade, list):
        for rule in downgrade:
            if not isinstance(rule, dict):
                continue
            trigger = rule.get("trigger_signal")
            max_rec = rule.get("max_recommendation")
            if trigger and str(trigger) in signal_ids and max_rec:
                tone_constraint = str(max_rec)
                return ESLDecisionResult(
                    decision="allow_with_constraints",
                    reason_code="downgrade_rule",
                    sensitivity_level=_sensitivity_from_mapping(signal_ids, policy),
                    tone_constraint=tone_constraint,
                )

    # 5. Pack sensitivity_mapping
    sensitivity_level = _sensitivity_from_mapping(signal_ids, policy)

    # 6. Default → allow
    return ESLDecisionResult(
        decision="allow",
        reason_code="none",
        sensitivity_level=sensitivity_level,
        tone_constraint=None,
    )


def _sensitivity_from_mapping(signal_ids: set[str], policy: dict) -> str | None:
    """Return highest sensitivity_level from signals present, or None."""
    mapping = policy.get("sensitivity_mapping") or {}
    if not isinstance(mapping, dict):
        return None
    # Order: high > medium > low (arbitrary; pack defines levels)
    levels_found: list[str] = []
    for sid in signal_ids:
        level = mapping.get(sid)
        if level is not None:
            levels_found.append(str(level))
    if not levels_found:
        return None
    # Prefer "high" if any signal maps to it
    for preferred in ("high", "medium", "low"):
        if preferred in levels_found:
            return preferred
    return levels_found[0] if levels_found else None
