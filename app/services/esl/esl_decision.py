"""ESL decision gate — allow/allow_with_constraints/suppress (Issue #175).

Evaluates signals + pack policy → ESL decision. Core hard bans enforced first;
pack policy (blocked_signals, prohibited_combinations, downgrade_rules,
sensitivity_mapping) applied after. Legacy pack=None → allow.

Issue #148 M2: Sensitivity from optional core taxonomy + pack sensitivity_mapping;
pack overrides core for same signal; highest level wins (high > medium > low).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.packs.loader import Pack

_ALLOWED_LEVELS = ("high", "medium", "low")


ESLDecision = Literal["allow", "allow_with_constraints", "suppress"]

# Signal IDs that always trigger suppress (core ethical bans). Cannot be overridden by pack.
# Empty for now; extend when domain-specific core-ban signals are defined (e.g. distress).
# See docs/CORE_BAN_SIGNAL_IDS.md for extension guidance.
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
    core_taxonomy: dict[str, Any] | None = None
    try:
        from app.core_taxonomy.loader import load_core_taxonomy

        core_taxonomy = load_core_taxonomy()
    except (FileNotFoundError, ValueError) as e:
        logging.getLogger(__name__).debug(
            "Core taxonomy unavailable, using pack-only sensitivity: %s", e
        )
        core_taxonomy = None

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
                    sensitivity_level=get_effective_sensitivity_level(
                        signal_ids, core_taxonomy, policy
                    ),
                    tone_constraint=tone_constraint,
                )

    # 5. Core default + pack sensitivity_mapping (M2)
    sensitivity_level = get_effective_sensitivity_level(
        signal_ids, core_taxonomy, policy
    )

    # 6. Default → allow
    return ESLDecisionResult(
        decision="allow",
        reason_code="none",
        sensitivity_level=sensitivity_level,
        tone_constraint=None,
    )


def _core_sensitivity(signal_id: str, core_taxonomy: dict[str, Any] | None) -> str | None:
    """Return core taxonomy sensitivity for signal_id, or None."""
    if not core_taxonomy:
        return None
    signals = core_taxonomy.get("signals")
    if not isinstance(signals, dict):
        return None
    entry = signals.get(signal_id)
    if not isinstance(entry, dict):
        return None
    sens = entry.get("sensitivity")
    return sens if sens in _ALLOWED_LEVELS else None


def get_effective_sensitivity_level(
    signal_ids: set[str],
    core_taxonomy: dict[str, Any] | None,
    esl_policy: dict,
) -> str | None:
    """Return effective sensitivity level from core default + pack mapping (Issue #148 M2).

    (1) From core taxonomy per-signal sensitivity collect levels.
    (2) From policy sensitivity_mapping collect levels.
    (3) Merge: pack overrides for same signal; then highest wins (high > medium > low).
    When core_taxonomy is None, behavior is pack-only (legacy).
    """
    pack_mapping = esl_policy.get("sensitivity_mapping") or {}
    if not isinstance(pack_mapping, dict):
        pack_mapping = {}

    levels_found: list[str] = []
    for sid in signal_ids:
        pack_level = pack_mapping.get(sid)
        if pack_level is not None and str(pack_level) in _ALLOWED_LEVELS:
            levels_found.append(str(pack_level))
        else:
            core_level = _core_sensitivity(sid, core_taxonomy)
            if core_level is not None:
                levels_found.append(core_level)

    if not levels_found:
        return None
    for preferred in _ALLOWED_LEVELS:
        if preferred in levels_found:
            return preferred
    return levels_found[0]
