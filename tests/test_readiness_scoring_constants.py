"""Tests for v2 readiness scoring constants and decay functions (Issue #85)."""

from __future__ import annotations

import pytest

from app.services.readiness.scoring_constants import (
    COMPOSITE_WEIGHTS,
    BASE_SCORES_COMPLEXITY,
    BASE_SCORES_LEADERSHIP_GAP,
    BASE_SCORES_MOMENTUM,
    BASE_SCORES_PRESSURE,
    CAP_DIMENSION_MAX,
    CAP_FOUNDER_URGENCY,
    CAP_JOBS_COMPLEXITY,
    CAP_JOBS_MOMENTUM,
    decay_complexity,
    decay_momentum,
    decay_pressure,
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
