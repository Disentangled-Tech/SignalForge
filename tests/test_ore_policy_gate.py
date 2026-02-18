"""ORE policy gate unit tests (Issue #124)."""

from __future__ import annotations

import pytest

from app.services.ore.policy_gate import check_policy_gate


def test_cooldown_active_observe_only() -> None:
    """Cooldown active → Observe Only, no draft."""
    result = check_policy_gate(
        cooldown_active=True,
        stability_modifier=0.8,
        alignment_high=True,
    )
    assert result.recommendation_type == "Observe Only"
    assert result.should_generate_draft is False
    assert "Cooldown" in str(result.safeguards_triggered)


def test_stability_cap_soft_value_share() -> None:
    """SM < 0.7 → Soft Value Share."""
    result = check_policy_gate(
        cooldown_active=False,
        stability_modifier=0.5,
        alignment_high=True,
    )
    assert result.recommendation_type == "Soft Value Share"
    assert result.should_generate_draft is True
    assert any("0.7" in s for s in result.safeguards_triggered)


def test_high_stability_low_pressure_intro() -> None:
    """SM >= 0.7, no cooldown, high alignment → Low-Pressure Intro."""
    result = check_policy_gate(
        cooldown_active=False,
        stability_modifier=0.8,
        alignment_high=True,
    )
    assert result.recommendation_type == "Low-Pressure Intro"
    assert result.should_generate_draft is True
