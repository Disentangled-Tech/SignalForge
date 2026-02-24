"""ORE policy gate unit tests (Issue #124)."""

from __future__ import annotations

from types import SimpleNamespace

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


# ── Phase 5: Pack-driven stability cap threshold ─────────────────────────────


def test_pack_driven_stability_cap_threshold_triggers_cap() -> None:
    """With pack having stability_cap_threshold: 0.5, SM=0.4 triggers cap."""
    pack = SimpleNamespace(esl_policy={"stability_cap_threshold": 0.5})
    result = check_policy_gate(
        cooldown_active=False,
        stability_modifier=0.4,
        alignment_high=True,
        pack=pack,
    )
    assert result.recommendation_type == "Soft Value Share"
    assert any("0.5" in s for s in result.safeguards_triggered)


def test_pack_driven_stability_cap_threshold_no_cap_when_above() -> None:
    """With pack having stability_cap_threshold: 0.5, SM=0.6 does not trigger cap."""
    pack = SimpleNamespace(esl_policy={"stability_cap_threshold": 0.5})
    result = check_policy_gate(
        cooldown_active=False,
        stability_modifier=0.6,
        alignment_high=True,
        pack=pack,
    )
    assert result.recommendation_type == "Low-Pressure Intro"
    assert not any("Stability cap" in s for s in result.safeguards_triggered)


def test_pack_none_uses_default_threshold() -> None:
    """With pack=None, 0.7 used (backward compatible)."""
    result = check_policy_gate(
        cooldown_active=False,
        stability_modifier=0.6,
        alignment_high=True,
        pack=None,
    )
    assert result.recommendation_type == "Soft Value Share"
    assert any("0.7" in s for s in result.safeguards_triggered)
