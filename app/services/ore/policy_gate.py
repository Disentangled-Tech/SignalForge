"""ORE policy gate — safety and ethics checks (Issue #124).

Checks before generation:
- Cooldown active? → output "Observe Only" (no draft)
- Stability cap triggered (SM < 0.7)? → max recommendation = Soft Value Share
- Low alignment? → require manual confirmation (not implemented)
"""

from __future__ import annotations

from dataclasses import dataclass


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
) -> PolicyGateResult:
    """Run policy gate checks.

    Args:
        cooldown_active: If True, no outreach — Observe Only.
        stability_modifier: ESL factor 0–1. If < 0.7, cap at Soft Value Share.
        alignment_high: If False, would require manual confirmation (deferred).

    Returns:
        PolicyGateResult with recommendation_type and whether to generate draft.
    """
    safeguards: list[str] = []

    if cooldown_active:
        return PolicyGateResult(
            recommendation_type="Observe Only",
            should_generate_draft=False,
            safeguards_triggered=["Cooldown active → Do not contact"],
        )

    if stability_modifier < 0.7:
        safeguards.append("Stability cap triggered (SM < 0.7) → Soft Value Share only")
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
