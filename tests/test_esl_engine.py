"""ESL engine unit tests (Issue #124, #106)."""

from __future__ import annotations

from datetime import date, datetime, timezone
import pytest

from app.services.esl.esl_engine import (
    build_esl_explain,
    compute_alignment_modifier,
    compute_base_engageability,
    compute_cadence_modifier,
    compute_csi,
    compute_esl_composite,
    compute_outreach_score,
    compute_spi,
    compute_stability_modifier,
    compute_svi,
    map_esl_to_recommendation,
)


# ── OutreachScore (existing) ──────────────────────────────────────────────


def test_outreach_score_trs_82_sm_05() -> None:
    """TRS=82, SM=0.5 → OutreachScore=41."""
    assert compute_outreach_score(82, 0.5) == 41


def test_outreach_score_trs_100_sm_1() -> None:
    """TRS=100, SM=1.0 → OutreachScore=100."""
    assert compute_outreach_score(100, 1.0) == 100


def test_outreach_score_trs_50_sm_07() -> None:
    """TRS=50, SM=0.7 → OutreachScore=35."""
    assert compute_outreach_score(50, 0.7) == 35


def test_outreach_score_rounds() -> None:
    """Fractional results are rounded."""
    assert compute_outreach_score(33, 0.5) == 16  # 16.5 → 16
    assert compute_outreach_score(33, 0.6) == 20  # 19.8 → 20


def test_outreach_score_zero_sm() -> None:
    """SM=0 → OutreachScore=0."""
    assert compute_outreach_score(82, 0.0) == 0


# ── BaseEngageability (Issue #106) ─────────────────────────────────────────


def test_base_engageability_trs_82() -> None:
    """TRS=82 → BE=0.82."""
    assert compute_base_engageability(82) == 0.82


def test_base_engageability_clamp_0_100() -> None:
    """TRS clamped to 0..100 for BE."""
    assert compute_base_engageability(0) == 0.0
    assert compute_base_engageability(100) == 1.0
    assert compute_base_engageability(-10) == 0.0
    assert compute_base_engageability(150) == 1.0


# ── StabilityModifier (Issue #106) ────────────────────────────────────────


def test_stability_modifier_svi_spi_csi_combine() -> None:
    """SM combines SVI, SPI, CSI; high stress → lower SM."""
    # All low stress → SM near 1
    assert compute_stability_modifier(0.0, 0.0, 1.0) > 0.9
    # High SVI → lower SM
    assert compute_stability_modifier(1.0, 0.0, 1.0) < compute_stability_modifier(
        0.0, 0.0, 1.0
    )


# ── CadenceModifier (Issue #106) ──────────────────────────────────────────


def test_cadence_modifier_cooldown_active() -> None:
    """Recent outreach (< 60 days) → CM=0."""
    from datetime import timedelta

    as_of = date(2026, 2, 18)
    last_outreach = datetime(2026, 2, 1, tzinfo=timezone.utc)  # 17 days ago
    assert compute_cadence_modifier(last_outreach, as_of) == 0.0


def test_cadence_modifier_no_recent_outreach() -> None:
    """No outreach in 60+ days → CM=1."""
    as_of = date(2026, 2, 18)
    last_outreach = datetime(2025, 11, 1, tzinfo=timezone.utc)  # 109 days ago
    assert compute_cadence_modifier(last_outreach, as_of) == 1.0


def test_cadence_modifier_none() -> None:
    """No outreach history → CM=1."""
    assert compute_cadence_modifier(None, date(2026, 2, 18)) == 1.0


# ── AlignmentModifier (Issue #106) ─────────────────────────────────────────


def test_alignment_modifier_ok_to_contact() -> None:
    """alignment_ok_to_contact=True → AM=1."""
    assert compute_alignment_modifier(True) == 1.0


def test_alignment_modifier_not_ok() -> None:
    """alignment_ok_to_contact=False → AM=0.5."""
    assert compute_alignment_modifier(False) == 0.5


def test_alignment_modifier_null() -> None:
    """alignment_ok_to_contact=None → AM=1 (default)."""
    assert compute_alignment_modifier(None) == 1.0


# ── ESL Composite (Issue #106) ────────────────────────────────────────────


def test_esl_composite_formula_be_times_sm_times_cm_times_am() -> None:
    """ESL = BE × SM × CM × AM."""
    # 0.82 * 0.65 * 1.0 * 1.0 = 0.533
    result = compute_esl_composite(0.82, 0.65, 1.0, 1.0)
    assert abs(result - 0.533) < 0.001


def test_esl_composite_cadence_zero() -> None:
    """CM=0 → ESL=0."""
    assert compute_esl_composite(0.82, 0.65, 0.0, 1.0) == 0.0


# ── Recommendation mapping (Issue #106) ───────────────────────────────────


def test_map_esl_to_recommendation_boundaries() -> None:
    """ESL boundaries map to correct engagement types."""
    assert map_esl_to_recommendation(0.0) == "Observe Only"
    assert map_esl_to_recommendation(0.1) == "Observe Only"
    assert map_esl_to_recommendation(0.2) == "Soft Value Share"
    assert map_esl_to_recommendation(0.3) == "Soft Value Share"
    assert map_esl_to_recommendation(0.4) == "Low-Pressure Intro"
    assert map_esl_to_recommendation(0.55) == "Low-Pressure Intro"
    assert map_esl_to_recommendation(0.7) == "Standard Outreach"
    assert map_esl_to_recommendation(0.8) == "Standard Outreach"
    assert map_esl_to_recommendation(0.9) == "Direct Strategic Outreach"
    assert map_esl_to_recommendation(1.0) == "Direct Strategic Outreach"


# ── SVI, SPI, CSI (Issue #106) ────────────────────────────────────────────


def test_svi_no_events() -> None:
    """No SVI events → SVI=0."""
    assert compute_svi([], date(2026, 2, 18)) == 0.0


def test_svi_urgency_events_recent() -> None:
    """Recent founder_urgency_language → SVI > 0."""
    ev = type("Ev", (), {"event_type": "founder_urgency_language", "event_time": datetime(2026, 2, 15, tzinfo=timezone.utc), "confidence": 0.8})()
    result = compute_svi([ev], date(2026, 2, 18))
    assert result > 0


def test_spi_no_snapshots() -> None:
    """No pressure snapshots → SPI=0."""
    assert compute_spi([], date(2026, 2, 18)) == 0.0


def test_spi_sustained_high_pressure() -> None:
    """Pressure >= 60 for 60+ days → SPI high."""
    snap = type("Snap", (), {"as_of": date(2026, 1, 1), "pressure": 70})()
    result = compute_spi([snap], date(2026, 2, 18))
    assert result >= 0.6


def test_csi_no_events() -> None:
    """No events → CSI=1 (default, no penalty)."""
    assert compute_csi([], date(2026, 2, 18)) == 1.0


def test_csi_few_events_no_gap() -> None:
    """Few events, no long gap → CSI high."""
    ev = type("Ev", (), {"event_time": datetime(2026, 2, 10, tzinfo=timezone.utc)})()
    result = compute_csi([ev], date(2026, 2, 18))
    assert result >= 0.9


# ── Explain payload (Issue #106) ───────────────────────────────────────────


def test_explain_includes_all_components() -> None:
    """Explain JSON includes BE, SM, CM, AM, SVI, SPI, CSI, ESL, recommendation."""
    explain = build_esl_explain(
        base_engageability=0.82,
        stability_modifier=0.65,
        cadence_modifier=1.0,
        alignment_modifier=1.0,
        svi=0.4,
        spi=0.5,
        csi=0.8,
        esl_composite=0.533,
        recommendation_type="Low-Pressure Intro",
    )
    assert explain["base_engageability"] == 0.82
    assert explain["stability_modifier"] == 0.65
    assert explain["cadence_modifier"] == 1.0
    assert explain["alignment_modifier"] == 1.0
    assert explain["svi"] == 0.4
    assert explain["spi"] == 0.5
    assert explain["csi"] == 0.8
    assert explain["esl_composite"] == 0.533
    assert explain["recommendation_type"] == "Low-Pressure Intro"
    assert "cadence_blocked" in explain
    assert "weights" in explain


# ── Policy gate integration (SM < 0.7 caps) ────────────────────────────────


def test_sm_under_07_caps_recommendation() -> None:
    """When SM < 0.7, policy gate caps at Soft Value Share."""
    from app.services.ore.policy_gate import check_policy_gate

    result = check_policy_gate(
        cooldown_active=False,
        stability_modifier=0.5,
        alignment_high=True,
    )
    assert result.recommendation_type == "Soft Value Share"
