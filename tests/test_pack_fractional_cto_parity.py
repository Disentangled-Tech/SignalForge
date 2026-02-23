"""CTO pack parity tests (Issue #189, Plan §4.3).

Golden tests: CTO pack must produce identical scores/ESL/recommendations as
current hardcoded constants. Prevents regression when extracting to YAML.
These tests will FAIL until readiness_engine, esl_engine accept pack parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.readiness.readiness_engine import compute_readiness
from app.services.esl.esl_engine import map_esl_to_recommendation


def _days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@dataclass
class MockEvent:
    event_type: str
    event_time: datetime
    confidence: float | None = 0.7


def _event(etype: str, days_ago: int, confidence: float | None = 0.7) -> MockEvent:
    return MockEvent(event_type=etype, event_time=_days_ago(days_ago), confidence=confidence)


class TestReadinessPackParity:
    """compute_readiness(events, as_of, pack=cto_pack) == compute_readiness(events, as_of)."""

    def test_funding_raised_parity(self) -> None:
        """Single funding_raised event: pack and no-pack produce same composite."""
        as_of = date.today()
        events = [_event("funding_raised", 5)]
        result_no_pack = compute_readiness(events, as_of)
        cto_pack = _get_cto_pack_or_skip()
        result_with_pack = compute_readiness(events, as_of, pack=cto_pack)
        assert result_with_pack["composite"] == result_no_pack["composite"]
        assert result_with_pack["momentum"] == result_no_pack["momentum"]

    def test_cto_role_posted_no_hired_parity(self) -> None:
        """cto_role_posted without cto_hired: leadership_gap=70 with both paths."""
        as_of = date.today()
        events = [_event("cto_role_posted", 50)]
        result_no_pack = compute_readiness(events, as_of)
        cto_pack = _get_cto_pack_or_skip()
        result_with_pack = compute_readiness(events, as_of, pack=cto_pack)
        assert result_with_pack["leadership_gap"] == result_no_pack["leadership_gap"]
        assert result_with_pack["leadership_gap"] == 70

    def test_multi_event_composite_parity(self) -> None:
        """Multiple events: pack and no-pack produce identical composite and dimensions."""
        as_of = date.today()
        events = [
            _event("funding_raised", 5),
            _event("job_posted_engineering", 10),
            _event("cto_role_posted", 50),
        ]
        result_no_pack = compute_readiness(events, as_of)
        cto_pack = _get_cto_pack_or_skip()
        result_with_pack = compute_readiness(events, as_of, pack=cto_pack)
        assert result_with_pack["composite"] == result_no_pack["composite"]
        assert result_with_pack["momentum"] == result_no_pack["momentum"]
        assert result_with_pack["complexity"] == result_no_pack["complexity"]
        assert result_with_pack["pressure"] == result_no_pack["pressure"]
        assert result_with_pack["leadership_gap"] == result_no_pack["leadership_gap"]


class TestEslPackParity:
    """map_esl_to_recommendation(esl, pack=cto_pack) == map_esl_to_recommendation(esl)."""

    def test_esl_boundary_parity(self) -> None:
        """ESL boundaries produce same recommendation with and without pack."""
        for esl_val, expected in [(0.1, "Observe Only"), (0.55, "Low-Pressure Intro"), (0.8, "Standard Outreach")]:
            result_no_pack = map_esl_to_recommendation(esl_val)
            cto_pack = _get_cto_pack_or_skip()
            result_with_pack = map_esl_to_recommendation(esl_val, pack=cto_pack)
            assert result_with_pack == result_no_pack == expected


def _get_cto_pack_or_skip():
    """Load fractional_cto_v1 pack; skip if loader not implemented."""
    try:
        from app.packs.loader import load_pack
        return load_pack("fractional_cto_v1", "1")
    except ImportError:
        pytest.skip("app.packs.loader not implemented")
    except (FileNotFoundError, ValueError, KeyError):
        pytest.skip("fractional_cto_v1 pack not installed")
