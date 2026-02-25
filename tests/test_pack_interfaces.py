"""Tests for pack engine interfaces (Phase 1, Plan Step 1.1)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.packs.interfaces import (
    PackAnalysisInterface,
    PackScoringInterface,
    adapt_pack_for_analysis,
    adapt_pack_for_scoring,
)


class TestPackScoringInterface:
    """Tests for PackScoringInterface and adapt_pack_for_scoring."""

    def test_adapt_pack_extracts_pain_signal_weights(self) -> None:
        pack = MagicMock()
        pack.scoring = {
            "pain_signal_weights": {"hiring_engineers": 15, "founder_overload": 10},
            "stage_bonuses": {"scaling_team": 20},
        }
        adapter = adapt_pack_for_scoring(pack)
        assert isinstance(adapter, PackScoringInterface)
        assert adapter.get_pain_signal_weights() == {
            "hiring_engineers": 15,
            "founder_overload": 10,
        }

    def test_adapt_pack_extracts_stage_bonuses(self) -> None:
        pack = MagicMock()
        pack.scoring = {
            "pain_signal_weights": {},
            "stage_bonuses": {"scaling_team": 20, "enterprise_transition": 30},
        }
        adapter = adapt_pack_for_scoring(pack)
        assert adapter.get_stage_bonuses() == {
            "scaling_team": 20,
            "enterprise_transition": 30,
        }

    def test_adapt_pack_handles_missing_keys(self) -> None:
        pack = MagicMock()
        pack.scoring = {}
        adapter = adapt_pack_for_scoring(pack)
        assert adapter.get_pain_signal_weights() == {}
        assert adapter.get_stage_bonuses() == {}

    def test_adapt_pack_handles_none_scoring(self) -> None:
        pack = MagicMock()
        pack.scoring = None
        adapter = adapt_pack_for_scoring(pack)
        assert adapter.get_pain_signal_weights() == {}
        assert adapter.get_stage_bonuses() == {}


class TestPackAnalysisInterface:
    """Tests for PackAnalysisInterface and adapt_pack_for_analysis."""

    def test_adapt_pack_returns_default_prompts(self) -> None:
        pack = MagicMock()
        adapter = adapt_pack_for_analysis(pack)
        assert isinstance(adapter, PackAnalysisInterface)
        assert adapter.get_stage_classification_prompt() == "stage_classification_v1"
        assert adapter.get_pain_signals_prompt() == "pain_signals_v1"
        assert adapter.get_explanation_prompt() == "explanation_v1"


@pytest.mark.integration
class TestPackInterfacesWithRealPack:
    """Integration tests with real fractional_cto_v1 pack."""

    def test_adapt_pack_for_scoring_with_fractional_cto_v1(self) -> None:
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        adapter = adapt_pack_for_scoring(pack)
        weights = adapter.get_pain_signal_weights()
        bonuses = adapter.get_stage_bonuses()
        assert "hiring_engineers" in weights
        assert weights["hiring_engineers"] == 15
        assert "scaling_team" in bonuses
        assert bonuses["scaling_team"] == 20
