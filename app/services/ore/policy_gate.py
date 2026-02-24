"""ORE policy gate — safety and ethics checks (Issue #124).

Checks before generation:
- Cooldown active? → output "Observe Only" (no draft)
- Stability cap triggered (SM < threshold)? → max recommendation = Soft Value Share
- Low alignment? → require manual confirmation (not implemented)

When pack is provided, uses pack.esl_policy.stability_cap_threshold (Phase 5).
When pack is None, uses default 0.7 (backward compatible).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.packs.loader import Pack

_DEFAULT_STABILITY_CAP_THRESHOLD = 0.7


def _get_stability_cap_threshold(pack: Pack | None) -> float:
    """Return stability cap threshold from pack or default (Phase 5)."""
    if pack is None:
        return _DEFAULT_STABILITY_CAP_THRESHOLD
    raw = pack.esl_policy.get("stability_cap_threshold", _DEFAULT_STABILITY_CAP_THRESHOLD)
    if isinstance(raw, (int, float)) and 0 <= raw <= 1:
        return float(raw)
    return _DEFAULT_STABILITY_CAP_THRESHOLD


@dataclass
class PolicyGateResult:
    """Result of policy gate check."""

    recommendation_type: str  # Observe Only | Soft Value Share | Low-Pressure Intro | etc.
    should_generate_draft: bool  # False when Observe Only
    safeguards_triggered: list[str]


def check_policy_gate(
    *,
    cooldown_active: bool,
    stability_modifier: float,
    alignment_high: bool = True,
    pack: Pack | None = None,
) -> PolicyGateResult:
    """Run policy gate checks.

    Args:
        cooldown_active: If True, no outreach — Observe Only.
        stability_modifier: ESL factor 0–1. If < threshold, cap at Soft Value Share.
        alignment_high: If False, would require manual confirmation (deferred).
        pack: Optional pack; when provided, uses pack.esl_policy.stability_cap_threshold.

    Returns:
        PolicyGateResult with recommendation_type and whether to generate draft.
    """
    safeguards: list[str] = []
    threshold = _get_stability_cap_threshold(pack)

    if cooldown_active:
        return PolicyGateResult(
            recommendation_type="Observe Only",
            should_generate_draft=False,
            safeguards_triggered=["Cooldown active → Do not contact"],
        )

    if stability_modifier < threshold:
        logger.info(
            "Stability cap triggered (SM < %s): capping recommendation to Soft Value Share",
            threshold,
            extra={"stability_modifier": stability_modifier, "threshold": threshold},
        )
        safeguards.append(
            f"Stability cap triggered (SM < {threshold}) → Soft Value Share only"
        )
        return PolicyGateResult(
            recommendation_type="Soft Value Share",
            should_generate_draft=True,
            safeguards_triggered=safeguards,
        )

    # High stability, no cooldown, high alignment → allow higher outreach types
    if alignment_high:
        return PolicyGateResult(
            recommendation_type="Low-Pressure Intro",
            should_generate_draft=True,
            safeguards_triggered=safeguards,
        )

    return PolicyGateResult(
        recommendation_type="Soft Value Share",
        should_generate_draft=True,
        safeguards_triggered=safeguards,
    )
