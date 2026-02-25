"""Tests for v2 readiness scoring constants and decay functions (Issue #85)."""

from __future__ import annotations

import pytest

from app.services.readiness.scoring_constants import (
    BASE_SCORES_COMPLEXITY,
    BASE_SCORES_LEADERSHIP_GAP,
    BASE_SCORES_MOMENTUM,
    BASE_SCORES_PRESSURE,
    CAP_DIMENSION_MAX,
    CAP_FOUNDER_URGENCY,
    CAP_JOBS_COMPLEXITY,
    CAP_JOBS_MOMENTUM,
    COMPOSITE_WEIGHTS,
    DEFAULT_DECAY_COMPLEXITY,
    DEFAULT_DECAY_MOMENTUM,
    DEFAULT_DECAY_PRESSURE,
    QUIET_SIGNAL_AMPLIFIED_BASE,
    QUIET_SIGNAL_LOOKBACK_DAYS,
    SUPPRESS_CTO_HIRED_60_DAYS,
    SUPPRESS_CTO_HIRED_180_DAYS,
    decay_complexity,
    decay_momentum,
    decay_pressure,
    from_pack,
)

# ── decay_momentum boundary tests ──────────────────────────────────────

class TestDecayMomentum:
    """decay_momentum returns correct values at boundary days (v2-spec §4.2)."""

    @pytest.mark.parametrize(
        ("days", "expected"),
        [
            (0, 1.0),
            (30, 1.0),
            (31, 0.7),
            (60, 0.7),
            (61, 0.4),
            (90, 0.4),
            (91, 0.0),
            (120, 0.0),
        ],
    )
    def test_boundary_days(self, days: int, expected: float) -> None:
        assert decay_momentum(days) == expected

    def test_negative_days_treated_as_zero(self) -> None:
        """Negative days are clamped to 0 (same as day 0)."""
        assert decay_momentum(-1) == 1.0
        assert decay_momentum(-100) == 1.0


# ── decay_pressure boundary tests ──────────────────────────────────────

class TestDecayPressure:
    """decay_pressure returns correct values at boundary days (v2-spec §4.2)."""

    @pytest.mark.parametrize(
        ("days", "expected"),
        [
            (0, 1.0),
            (30, 1.0),
            (31, 0.85),
            (60, 0.85),
            (61, 0.6),
            (120, 0.6),
            (121, 0.2),
            (365, 0.2),
        ],
    )
    def test_boundary_days(self, days: int, expected: float) -> None:
        assert decay_pressure(days) == expected

    def test_negative_days_treated_as_zero(self) -> None:
        """Negative days are clamped to 0 (same as day 0)."""
        assert decay_pressure(-1) == 1.0
        assert decay_pressure(-100) == 1.0


# ── decay_complexity boundary tests ────────────────────────────────────

class TestDecayComplexity:
    """decay_complexity returns correct values at boundary days (v2-spec §4.2)."""

    @pytest.mark.parametrize(
        ("days", "expected"),
        [
            (0, 1.0),
            (90, 1.0),
            (91, 0.8),
            (180, 0.8),
            (181, 0.6),
            (365, 0.6),
            (366, 0.4),
            (500, 0.4),
        ],
    )
    def test_boundary_days(self, days: int, expected: float) -> None:
        assert decay_complexity(days) == expected

    def test_negative_days_treated_as_zero(self) -> None:
        """Negative days are clamped to 0 (same as day 0)."""
        assert decay_complexity(-1) == 1.0
        assert decay_complexity(-100) == 1.0


# ── Constants exist and are non-empty ───────────────────────────────────

class TestConstantsExist:
    """All constants are defined and non-empty."""

    def test_base_scores_momentum(self) -> None:
        assert BASE_SCORES_MOMENTUM
        assert "funding_raised" in BASE_SCORES_MOMENTUM
        assert BASE_SCORES_MOMENTUM["funding_raised"] == 35
        assert BASE_SCORES_MOMENTUM["job_posted_engineering"] == 10

    def test_base_scores_complexity(self) -> None:
        assert BASE_SCORES_COMPLEXITY
        assert "api_launched" in BASE_SCORES_COMPLEXITY
        assert BASE_SCORES_COMPLEXITY["api_launched"] == 25

    def test_base_scores_pressure(self) -> None:
        assert BASE_SCORES_PRESSURE
        assert "regulatory_deadline" in BASE_SCORES_PRESSURE
        assert BASE_SCORES_PRESSURE["regulatory_deadline"] == 30

    def test_base_scores_leadership_gap(self) -> None:
        assert BASE_SCORES_LEADERSHIP_GAP
        assert "cto_role_posted" in BASE_SCORES_LEADERSHIP_GAP
        assert BASE_SCORES_LEADERSHIP_GAP["cto_role_posted"] == 70

    def test_caps(self) -> None:
        assert CAP_JOBS_MOMENTUM == 30
        assert CAP_JOBS_COMPLEXITY == 20
        assert CAP_FOUNDER_URGENCY == 30
        assert CAP_DIMENSION_MAX == 100

    def test_composite_weights(self) -> None:
        assert COMPOSITE_WEIGHTS
        assert COMPOSITE_WEIGHTS["M"] == 0.30
        assert COMPOSITE_WEIGHTS["C"] == 0.30
        assert COMPOSITE_WEIGHTS["P"] == 0.25
        assert COMPOSITE_WEIGHTS["G"] == 0.15

    def test_quiet_signal_amplification_constants(self) -> None:
        """QUIET_SIGNAL_AMPLIFIED_BASE exists with expected structure (Issue #113)."""
        assert QUIET_SIGNAL_LOOKBACK_DAYS == 365
        assert "job_posted_infra" in QUIET_SIGNAL_AMPLIFIED_BASE
        assert QUIET_SIGNAL_AMPLIFIED_BASE["job_posted_infra"] == {"M": 20, "C": 20}
        assert QUIET_SIGNAL_AMPLIFIED_BASE["compliance_mentioned"] == {"C": 25}
        assert QUIET_SIGNAL_AMPLIFIED_BASE["api_launched"] == {"C": 35}


# ── from_pack decay and suppressors (Issue #174) ────────────────────────────


class TestFromPackDecayAndSuppressors:
    """from_pack() parses decay and suppressors from pack config."""

    def test_from_pack_empty_returns_default_decay_and_suppressors(self) -> None:
        """Empty config returns default decay breakpoints and suppressors."""
        cfg = from_pack({})
        assert cfg["decay_momentum"] == DEFAULT_DECAY_MOMENTUM
        assert cfg["decay_pressure"] == DEFAULT_DECAY_PRESSURE
        assert cfg["decay_complexity"] == DEFAULT_DECAY_COMPLEXITY
        assert cfg["suppress_cto_hired_60_days"] == SUPPRESS_CTO_HIRED_60_DAYS
        assert cfg["suppress_cto_hired_180_days"] == SUPPRESS_CTO_HIRED_180_DAYS

    def test_from_pack_decay_parses_momentum_breakpoints(self) -> None:
        """Pack decay.momentum parses to sorted (max_days, value) list."""
        cfg = from_pack({
            "decay": {
                "momentum": {"0-30": 1.0, "31-60": 0.7, "61-90": 0.4, "91+": 0.0},
            },
        })
        assert cfg["decay_momentum"] == [(30, 1.0), (60, 0.7), (90, 0.4), (9999, 0.0)]

    def test_from_pack_suppressors_override_defaults(self) -> None:
        """Pack suppressors override module defaults."""
        cfg = from_pack({
            "suppressors": {"cto_hired_60_days": 80, "cto_hired_180_days": 55},
        })
        assert cfg["suppress_cto_hired_60_days"] == 80
        assert cfg["suppress_cto_hired_180_days"] == 55

    def test_from_pack_partial_suppressors_uses_default_for_missing(self) -> None:
        """Partial suppressors: missing key uses default."""
        cfg = from_pack({"suppressors": {"cto_hired_60_days": 99}})
        assert cfg["suppress_cto_hired_60_days"] == 99
        assert cfg["suppress_cto_hired_180_days"] == SUPPRESS_CTO_HIRED_180_DAYS

    def test_from_pack_invalid_suppressor_falls_back_to_default(self) -> None:
        """Invalid suppressor value falls back to default."""
        cfg = from_pack({"suppressors": {"cto_hired_60_days": "not_a_number"}})
        assert cfg["suppress_cto_hired_60_days"] == SUPPRESS_CTO_HIRED_60_DAYS


class TestFromPackMinimumThresholdAndDisqualifierSignals:
    """from_pack() parses minimum_threshold and disqualifier_signals (Phase 2, Issue #174)."""

    def test_from_pack_minimum_threshold_default_zero(self) -> None:
        """Empty config returns minimum_threshold 0."""
        cfg = from_pack({})
        assert cfg["minimum_threshold"] == 0

    def test_from_pack_minimum_threshold_override(self) -> None:
        """Pack minimum_threshold overrides default."""
        cfg = from_pack({"minimum_threshold": 60})
        assert cfg["minimum_threshold"] == 60

    def test_from_pack_disqualifier_signals_empty_default(self) -> None:
        """Empty or missing disqualifier_signals returns empty dict."""
        assert from_pack({})["disqualifier_signals"] == {}
        assert from_pack({"disqualifier_signals": {}})["disqualifier_signals"] == {}

    def test_from_pack_disqualifier_signals_parses(self) -> None:
        """Pack disqualifier_signals parses to {event_type: window_days}."""
        cfg = from_pack({"disqualifier_signals": {"cto_hired": 180, "acquired": 365}})
        assert cfg["disqualifier_signals"] == {"cto_hired": 180, "acquired": 365}
