"""Unit tests for ORE dominant TRS dimension (Issue #117 M1)."""

from __future__ import annotations

from app.services.ore.dominant_dimension import get_dominant_trs_dimension


def test_single_winner_momentum() -> None:
    """When momentum is the only maximum, return 'momentum'."""
    assert (
        get_dominant_trs_dimension(
            momentum=80,
            complexity=20,
            pressure=10,
            leadership_gap=5,
        )
        == "momentum"
    )


def test_single_winner_complexity() -> None:
    """When complexity is the only maximum, return 'complexity'."""
    assert (
        get_dominant_trs_dimension(
            momentum=10,
            complexity=90,
            pressure=20,
            leadership_gap=5,
        )
        == "complexity"
    )


def test_single_winner_pressure() -> None:
    """When pressure is the only maximum, return 'pressure'."""
    assert (
        get_dominant_trs_dimension(
            momentum=10,
            complexity=20,
            pressure=85,
            leadership_gap=5,
        )
        == "pressure"
    )


def test_single_winner_leadership_gap() -> None:
    """When leadership_gap is the only maximum, return 'leadership_gap'."""
    assert (
        get_dominant_trs_dimension(
            momentum=10,
            complexity=20,
            pressure=15,
            leadership_gap=95,
        )
        == "leadership_gap"
    )


def test_tie_break_momentum_over_complexity() -> None:
    """Tie-break order M > C > P > G: momentum and complexity tied → momentum."""
    assert (
        get_dominant_trs_dimension(
            momentum=50,
            complexity=50,
            pressure=10,
            leadership_gap=10,
        )
        == "momentum"
    )


def test_tie_break_momentum_over_pressure() -> None:
    """Tie-break: momentum and pressure tied at max → momentum."""
    assert (
        get_dominant_trs_dimension(
            momentum=60,
            complexity=20,
            pressure=60,
            leadership_gap=20,
        )
        == "momentum"
    )


def test_tie_break_complexity_over_pressure() -> None:
    """Tie-break: complexity and pressure tied at max → complexity."""
    assert (
        get_dominant_trs_dimension(
            momentum=10,
            complexity=70,
            pressure=70,
            leadership_gap=10,
        )
        == "complexity"
    )


def test_tie_break_pressure_over_leadership_gap() -> None:
    """Tie-break: pressure and leadership_gap tied at max → pressure."""
    assert (
        get_dominant_trs_dimension(
            momentum=10,
            complexity=10,
            pressure=40,
            leadership_gap=40,
        )
        == "pressure"
    )


def test_all_equal_returns_momentum() -> None:
    """When all four dimensions are equal, return momentum (first in tie-break order)."""
    assert (
        get_dominant_trs_dimension(
            momentum=25,
            complexity=25,
            pressure=25,
            leadership_gap=25,
        )
        == "momentum"
    )


def test_all_zeros_returns_momentum() -> None:
    """When all dimensions are 0, return momentum (tie-break order)."""
    assert (
        get_dominant_trs_dimension(
            momentum=0,
            complexity=0,
            pressure=0,
            leadership_gap=0,
        )
        == "momentum"
    )


def test_three_way_tie_momentum_wins() -> None:
    """Momentum, complexity, pressure tied → momentum."""
    assert (
        get_dominant_trs_dimension(
            momentum=33,
            complexity=33,
            pressure=33,
            leadership_gap=0,
        )
        == "momentum"
    )


def test_four_way_tie_returns_momentum() -> None:
    """All four tied at same value → momentum."""
    assert (
        get_dominant_trs_dimension(
            momentum=100,
            complexity=100,
            pressure=100,
            leadership_gap=100,
        )
        == "momentum"
    )
