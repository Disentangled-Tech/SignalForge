"""Tests for v2 readiness dimension calculators (Issue #86)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.readiness.readiness_engine import (
    compute_complexity,
    compute_leadership_gap,
    compute_momentum,
    compute_pressure,
)


@dataclass
class MockEvent:
    """Minimal event-like object for testing."""

    event_type: str
    event_time: datetime
    confidence: float | None = 0.7


def _days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _event(etype: str, days_ago: int, confidence: float | None = 0.7) -> MockEvent:
    return MockEvent(event_type=etype, event_time=_days_ago(days_ago), confidence=confidence)


# ── Scenario 1: Funding + hiring spike → high M, jobs cap at 30 ───────────


class TestScenarioFundingHiringSpike:
    """Funding + hiring spike produces expected high M (Issue #86)."""

    def test_funding_and_three_jobs_caps_at_30_for_jobs(self) -> None:
        """5× job_posted_engineering (10 each) hits jobs cap 30; funding_raised adds ~25."""
        as_of = date.today()
        events = [
            _event("funding_raised", 5),
            _event("job_posted_engineering", 10),
            _event("job_posted_engineering", 10),
            _event("job_posted_engineering", 10),
            _event("job_posted_engineering", 10),
            _event("job_posted_engineering", 10),
        ]
        m = compute_momentum(events, as_of)
        # funding: 35 * 1.0 * 0.7 = 24.5; jobs: 5*10*1.0*0.7=35, cap 30
        # total = 24.5 + 30 = 54.5 → 54 or 55
        assert m >= 50
        assert m <= 100
        assert m in (54, 55)

    def test_momentum_high_with_funding_and_headcount(self) -> None:
        """funding_raised + headcount_growth produces high M."""
        events = [
            _event("funding_raised", 5),
            _event("headcount_growth", 10),
        ]
        m = compute_momentum(events, date.today())
        # 35*1.0*0.7 + 20*1.0*0.7 = 24.5 + 14 = 38.5 → 38 or 39
        assert m in (38, 39)


# ── Scenario 2: Complexity accumulation ───────────────────────────────────


class TestScenarioComplexityAccumulation:
    """Complexity events accumulate correctly (Issue #86)."""

    def test_complexity_accumulates_with_slow_decay(self) -> None:
        """api_launched (30d), ai_feature_launched (60d), compliance_mentioned (90d)."""
        as_of = date.today()
        events = [
            _event("api_launched", 30),
            _event("ai_feature_launched", 60),
            _event("compliance_mentioned", 90),
        ]
        c = compute_complexity(events, as_of)
        # All in 0-90 day decay = 1.0
        # 25*1.0*0.7 + 25*1.0*0.7 + 15*1.0*0.7 = 17.5 + 17.5 + 10.5 = 45.5 → 46
        assert c >= 40
        assert c <= 100
        assert c == 46


# ── Scenario 3: Leadership gap suppressed when CTO hired ───────────────────


class TestScenarioCtoHiredSuppressor:
    """Leadership gap suppressed when CTO hired (Issue #86)."""

    def test_cto_hired_within_60_days_suppresses_strongly(self) -> None:
        """cto_role_posted (100d ago) + cto_hired (45d ago) → G suppressed."""
        as_of = date.today()
        events = [
            _event("cto_role_posted", 100),
            _event("cto_hired", 45),
        ]
        g = compute_leadership_gap(events, as_of)
        # Raw G from cto_role_posted: 70 (in 120d window, no decay)
        # cto_hired in 60d: G = max(70 - 70, 0) = 0
        assert g == 0

    def test_cto_hired_within_180_days_suppresses_moderately(self) -> None:
        """cto_role_posted + cto_hired (100d ago) → G reduced by 50."""
        events = [
            _event("cto_role_posted", 50),
            _event("cto_hired", 100),
        ]
        g = compute_leadership_gap(events, date.today())
        # Raw G: 70; cto_hired in 61-180d: G = max(70 - 50, 0) = 20
        assert g == 20

    def test_no_cto_hired_yields_full_gap(self) -> None:
        """cto_role_posted without cto_hired → full G."""
        events = [_event("cto_role_posted", 50)]
        g = compute_leadership_gap(events, date.today())
        assert g == 70


# ── Decay boundaries ───────────────────────────────────────────────────────


class TestDecayBoundaries:
    """Decay applied correctly at day boundaries."""

    def test_momentum_decay_at_30_31_days(self) -> None:
        """Event at 30d: full; at 31d: 0.7."""
        as_of = date.today()
        e30 = [_event("funding_raised", 30)]
        e31 = [_event("funding_raised", 31)]
        m30 = compute_momentum(e30, as_of)
        m31 = compute_momentum(e31, as_of)
        # 35*1.0*0.7=24.5 vs 35*0.7*0.7=17.15
        assert m30 in (24, 25)  # round(24.5)
        assert m31 == 17

    def test_momentum_zero_after_91_days(self) -> None:
        """Events older than 90 days contribute 0 to momentum."""
        events = [_event("funding_raised", 95)]
        m = compute_momentum(events, date.today())
        assert m == 0

    def test_pressure_decay_at_boundaries(self) -> None:
        """Pressure decay: 30d=1.0, 31d=0.85, 121d=0.2."""
        as_of = date.today()
        p30 = compute_pressure([_event("enterprise_customer", 30)], as_of)
        p31 = compute_pressure([_event("enterprise_customer", 31)], as_of)
        p121 = compute_pressure([_event("enterprise_customer", 121)], as_of)
        # 25*1.0*0.7=17.5, 25*0.85*0.7=14.875, 25*0.2*0.7=3.5
        assert p30 in (17, 18)
        assert p31 == 15
        assert p121 in (3, 4)

    def test_complexity_slow_decay(self) -> None:
        """Complexity: 90d=1.0, 91d=0.8, 366d=0.4."""
        as_of = date.today()
        c90 = compute_complexity([_event("api_launched", 90)], as_of)
        c91 = compute_complexity([_event("api_launched", 91)], as_of)
        c366 = compute_complexity([_event("api_launched", 366)], as_of)
        assert c90 in (17, 18)  # 25*1.0*0.7=17.5
        assert c91 == 14  # 25*0.8*0.7=14
        assert c366 == 7  # 25*0.4*0.7=7


# ── Caps ────────────────────────────────────────────────────────────────────


class TestCaps:
    """Caps applied correctly."""

    def test_momentum_jobs_cap_30(self) -> None:
        """Five job_posted_engineering events → jobs subscore capped at 30."""
        events = [_event("job_posted_engineering", i) for i in range(5)]
        m = compute_momentum(events, date.today())
        # 5 * 10 * 1.0 * 0.7 = 35, but jobs cap = 30
        assert m == 30

    def test_pressure_founder_urgency_cap_30(self) -> None:
        """Three founder_urgency_language events → cap at 30."""
        events = [
            _event("founder_urgency_language", 5),
            _event("founder_urgency_language", 10),
            _event("founder_urgency_language", 15),
        ]
        p = compute_pressure(events, date.today())
        # 3*15*1.0*0.7 = 31.5, cap 30
        assert p == 30

    def test_complexity_job_posted_infra_cap_20(self) -> None:
        """Three job_posted_infra → cap at 20 for that bucket."""
        events = [
            _event("job_posted_infra", 10),
            _event("job_posted_infra", 20),
            _event("job_posted_infra", 30),
        ]
        c = compute_complexity(events, date.today())
        # 3*10*1.0*0.7 = 21, cap 20
        assert c == 20

    def test_dimension_scores_capped_at_100(self) -> None:
        """No dimension exceeds 100."""
        events = [
            _event("funding_raised", 1),
            _event("headcount_growth", 1),
            _event("launch_major", 1),
            _event("job_posted_engineering", 1),
            _event("job_posted_engineering", 2),
            _event("job_posted_engineering", 3),
        ]
        m = compute_momentum(events, date.today())
        assert m <= 100


# ── Confidence weighting ───────────────────────────────────────────────────


class TestConfidenceWeighting:
    """Confidence affects contribution."""

    def test_confidence_half_contributes_half(self) -> None:
        """Event with confidence 0.5 contributes half."""
        full = [_event("funding_raised", 5, confidence=1.0)]
        half = [_event("funding_raised", 5, confidence=0.5)]
        m_full = compute_momentum(full, date.today())
        m_half = compute_momentum(half, date.today())
        # 35*1.0*1.0=35 vs 35*1.0*0.5=17.5
        assert m_full == 35
        assert m_half == 18

    def test_none_confidence_defaults_to_07(self) -> None:
        """None confidence treated as 0.7."""
        e = MockEvent(event_type="funding_raised", event_time=_days_ago(5), confidence=None)
        m = compute_momentum([e], date.today())
        assert m in (24, 25)  # 35*1.0*0.7=24.5


# ── Edge cases ──────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Empty events, unknown types, etc."""

    def test_empty_events_returns_zero(self) -> None:
        """All dimensions return 0 for empty events."""
        as_of = date.today()
        assert compute_momentum([], as_of) == 0
        assert compute_complexity([], as_of) == 0
        assert compute_pressure([], as_of) == 0
        assert compute_leadership_gap([], as_of) == 0

    def test_unknown_event_types_ignored(self) -> None:
        """Events with unknown event_type are ignored."""
        events = [
            MockEvent("unknown_type", _days_ago(5), 1.0),
            _event("funding_raised", 5),
        ]
        m = compute_momentum(events, date.today())
        assert m in (24, 25)  # only funding counts; 35*1.0*0.7=24.5

    def test_leadership_gap_positive_signals_sum(self) -> None:
        """cto_role_posted + no_cto_detected reinforce (cap 100)."""
        events = [
            _event("cto_role_posted", 50),
            _event("no_cto_detected", 100),
        ]
        g = compute_leadership_gap(events, date.today())
        # 70 + 40 = 110, cap 100
        assert g == 100
