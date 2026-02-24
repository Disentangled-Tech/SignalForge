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


class TestNormalizePackParity:
    """normalize_raw_event(..., pack=cto_pack) accepts same events as pack=None (Phase 2, Step 3.3)."""

    def test_normalize_with_pack_accepts_taxonomy_events(self) -> None:
        """Events in pack taxonomy are accepted with pack; same as without pack."""
        from app.ingestion.normalize import normalize_raw_event
        from app.schemas.signal import RawEvent

        raw = RawEvent(
            company_name="Test Co",
            event_type_candidate="funding_raised",
            event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
        )
        result_no_pack = normalize_raw_event(raw, "test")
        cto_pack = _get_cto_pack_or_skip()
        result_with_pack = normalize_raw_event(raw, "test", pack=cto_pack)
        assert result_no_pack is not None
        assert result_with_pack is not None
        assert result_with_pack[0]["event_type"] == result_no_pack[0]["event_type"]


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


class TestSviPackParity:
    """compute_svi(events, as_of, pack=cto_pack) == compute_svi(events, as_of) (Phase 2, Step 3.4)."""

    def test_svi_event_types_parity(self) -> None:
        """SVI with funding_raised (SVI event type) produces same result with and without pack."""
        from app.services.esl.esl_engine import compute_svi

        as_of = date.today()
        events = [_event("funding_raised", 5)]
        result_no_pack = compute_svi(events, as_of)
        cto_pack = _get_cto_pack_or_skip()
        result_with_pack = compute_svi(events, as_of, pack=cto_pack)
        assert result_with_pack == result_no_pack


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
    """calculate_score(..., pack=cto_pack) == calculate_score(...) (Issue #189, Plan Step 1.5).

    Phase 2: pack=None now resolves default pack from filesystem, so both paths
    use the same pack and produce identical scores.
    """

    def test_pain_signal_weights_parity(self) -> None:
        """Pain-signal weights from pack produce same score as defaults."""
        from app.services.scoring import calculate_score

        cto_pack = _get_cto_pack_or_skip()
        keys = list((cto_pack.scoring or {}).get("pain_signal_weights") or {})

        def _signals(true_keys: list[str]) -> dict:
            return {"signals": {k: {"value": k in true_keys, "why": "test"} for k in keys}}

        # hiring_engineers(15) + founder_overload(10) = 25
        signals = _signals(["hiring_engineers", "founder_overload"])
        score_no_pack = calculate_score(signals, "")
        score_with_pack = calculate_score(signals, "", pack=cto_pack)
        assert score_with_pack == score_no_pack == 25

    def test_stage_bonuses_parity(self) -> None:
        """Stage bonuses from pack produce same score as defaults."""
        from app.services.scoring import calculate_score

        cto_pack = _get_cto_pack_or_skip()
        keys = list((cto_pack.scoring or {}).get("pain_signal_weights") or {})

        def _signals(true_keys: list[str]) -> dict:
            return {"signals": {k: {"value": k in true_keys, "why": "test"} for k in keys}}

        # No signals, scaling_team bonus = 20
        signals = _signals([])
        score_no_pack = calculate_score(signals, "scaling_team")
        score_with_pack = calculate_score(signals, "scaling_team", pack=cto_pack)
        assert score_with_pack == score_no_pack == 20

    def test_combined_signals_and_stage_parity(self) -> None:
        """Signals + stage bonus from pack match defaults (Issue #189, Plan Step 1.5)."""
        from app.services.scoring import calculate_score

        cto_pack = _get_cto_pack_or_skip()
        keys = list((cto_pack.scoring or {}).get("pain_signal_weights") or {})

        def _signals(true_keys: list[str]) -> dict:
            return {"signals": {k: {"value": k in true_keys, "why": "test"} for k in keys}}

        # compliance(25) + product_delivery(20) + struggling_execution(30) = 75
        signals = _signals(["compliance_security_pressure", "product_delivery_issues"])
        score_no_pack = calculate_score(signals, "struggling_execution")
        score_with_pack = calculate_score(signals, "struggling_execution", pack=cto_pack)
        assert score_with_pack == score_no_pack == 75


class TestOrePlaybookParity:
    """get_ore_playbook(cto_pack) matches module constants (Phase 2, Step 3.5)."""

    def test_playbook_pattern_frames_match_constants(self) -> None:
        """Pack ore_outreach pattern_frames match PATTERN_FRAMES."""
        from app.services.ore.draft_generator import PATTERN_FRAMES, get_ore_playbook

        cto_pack = _get_cto_pack_or_skip()
        playbook = get_ore_playbook(cto_pack)
        for key in PATTERN_FRAMES:
            assert key in playbook["pattern_frames"]
            assert playbook["pattern_frames"][key] == PATTERN_FRAMES[key]

    def test_playbook_value_assets_match_constants(self) -> None:
        """Pack ore_outreach value_assets match VALUE_ASSETS."""
        from app.services.ore.draft_generator import VALUE_ASSETS, get_ore_playbook

        cto_pack = _get_cto_pack_or_skip()
        playbook = get_ore_playbook(cto_pack)
        assert playbook["value_assets"] == VALUE_ASSETS

    def test_playbook_ctas_match_constants(self) -> None:
        """Pack ore_outreach ctas match CTAS."""
        from app.services.ore.draft_generator import CTAS, get_ore_playbook

        cto_pack = _get_cto_pack_or_skip()
        playbook = get_ore_playbook(cto_pack)
        assert playbook["ctas"] == CTAS

    def test_playbook_none_returns_constants(self) -> None:
        """get_ore_playbook(None) returns module constants (fallback)."""
        from app.services.ore.draft_generator import (
            CTAS,
            PATTERN_FRAMES,
            VALUE_ASSETS,
            get_ore_playbook,
        )

        playbook = get_ore_playbook(None)
        assert playbook["pattern_frames"] == PATTERN_FRAMES
        assert playbook["value_assets"] == VALUE_ASSETS
        assert playbook["ctas"] == CTAS


def _get_cto_pack_or_skip():
    """Load fractional_cto_v1 pack; skip if loader not implemented."""
    try:
        from app.packs.loader import load_pack

        return load_pack("fractional_cto_v1", "1")
    except ImportError:
        pytest.skip("app.packs.loader not implemented")
    except (FileNotFoundError, ValueError, KeyError):
        pytest.skip("fractional_cto_v1 pack not installed")
