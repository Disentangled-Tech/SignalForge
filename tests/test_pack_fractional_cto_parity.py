"""CTO pack parity tests (Issue #189, Plan §4.3).

Golden tests: CTO pack must produce identical scores/ESL/recommendations as
current hardcoded constants. Prevents regression when extracting to YAML.
These tests will FAIL until readiness_engine, esl_engine accept pack parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest

from app.services.esl.esl_engine import map_esl_to_recommendation
from app.services.readiness.readiness_engine import compute_readiness


def _days_ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


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
        for esl_val, expected in [
            (0.1, "Observe Only"),
            (0.55, "Low-Pressure Intro"),
            (0.8, "Standard Outreach"),
        ]:
            result_no_pack = map_esl_to_recommendation(esl_val)
            cto_pack = _get_cto_pack_or_skip()
            result_with_pack = map_esl_to_recommendation(esl_val, pack=cto_pack)
            assert result_with_pack == result_no_pack == expected


class TestScoringPackParity:
    """calculate_score(..., pack=cto_pack) == calculate_score(...) (Issue #189, Plan Step 1.5)."""

    def test_pain_signal_weights_parity(self) -> None:
        """Pain-signal weights from pack produce same score as defaults."""
        from app.services.scoring import DEFAULT_SIGNAL_WEIGHTS, calculate_score

        def _signals(true_keys: list[str]) -> dict:
            return {
                "signals": {
                    k: {"value": k in true_keys, "why": "test"} for k in DEFAULT_SIGNAL_WEIGHTS
                }
            }

        cto_pack = _get_cto_pack_or_skip()
        # hiring_engineers(15) + founder_overload(10) = 25
        signals = _signals(["hiring_engineers", "founder_overload"])
        score_no_pack = calculate_score(signals, "")
        score_with_pack = calculate_score(signals, "", pack=cto_pack)
        assert score_with_pack == score_no_pack == 25

    def test_stage_bonuses_parity(self) -> None:
        """Stage bonuses from pack produce same score as defaults."""
        from app.services.scoring import DEFAULT_SIGNAL_WEIGHTS, calculate_score

        def _signals(true_keys: list[str]) -> dict:
            return {
                "signals": {
                    k: {"value": k in true_keys, "why": "test"} for k in DEFAULT_SIGNAL_WEIGHTS
                }
            }

        cto_pack = _get_cto_pack_or_skip()
        # No signals, scaling_team bonus = 20
        signals = _signals([])
        score_no_pack = calculate_score(signals, "scaling_team")
        score_with_pack = calculate_score(signals, "scaling_team", pack=cto_pack)
        assert score_with_pack == score_no_pack == 20

    def test_combined_signals_and_stage_parity(self) -> None:
        """Signals + stage bonus from pack match defaults (Issue #189, Plan Step 1.5)."""
        from app.services.scoring import DEFAULT_SIGNAL_WEIGHTS, calculate_score

        def _signals(true_keys: list[str]) -> dict:
            return {
                "signals": {
                    k: {"value": k in true_keys, "why": "test"} for k in DEFAULT_SIGNAL_WEIGHTS
                }
            }

        cto_pack = _get_cto_pack_or_skip()
        # compliance(25) + product_delivery(20) + struggling_execution(30) = 75
        signals = _signals(["compliance_security_pressure", "product_delivery_issues"])
        score_no_pack = calculate_score(signals, "struggling_execution")
        score_with_pack = calculate_score(signals, "struggling_execution", pack=cto_pack)
        assert score_with_pack == score_no_pack == 75


def _get_cto_pack_or_skip():
    """Load fractional_cto_v1 pack; skip if loader not implemented."""
    try:
        from app.packs.loader import load_pack

        return load_pack("fractional_cto_v1", "1")
    except ImportError:
        pytest.skip("app.packs.loader not implemented")
    except (FileNotFoundError, ValueError, KeyError):
        pytest.skip("fractional_cto_v1 pack not installed")
