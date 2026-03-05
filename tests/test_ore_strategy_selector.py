"""Unit tests for ORE strategy selector (Issue #117 M2)."""

from __future__ import annotations

import copy

import pytest

from app.services.ore.strategy_selector import (
    StrategySelectorResult,
    select_outreach_strategy,
)


def _minimal_playbook() -> dict:
    """Playbook with all four pattern_frames and lists (no channels, no soft_ctas)."""
    return {
        "pattern_frames": {
            "momentum": "Momentum framing text.",
            "complexity": "Complexity framing text.",
            "pressure": "When timelines get tighter, reduce decision load.",
            "leadership_gap": "When there isn't a dedicated technical owner yet.",
        },
        "value_assets": [
            "2-page Tech Inflection Checklist",
            "30-minute map",
            "5 questions",
        ],
        "ctas": [
            "Want me to send that checklist?",
            "Open to a 15-min call?",
            "If helpful, I can share a one-page approach.",
        ],
    }


class TestPatternFrameByDominantDimension:
    """pattern_frame is chosen from dominant_dimension with fallback."""

    def test_momentum_dominant_returns_momentum_frame(self) -> None:
        """Momentum-dominant → pattern_frame is momentum framing."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.pattern_frame == "Momentum framing text."

    def test_complexity_dominant_returns_complexity_frame(self) -> None:
        """Complexity-dominant → pattern_frame is complexity framing."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="complexity",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.pattern_frame == "Complexity framing text."

    def test_pressure_dominant_returns_pressure_frame(self) -> None:
        """Pressure-dominant → pattern_frame is pressure/stabilization framing."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Soft Value Share",
            dominant_dimension="pressure",
            alignment_high=False,
            playbook=playbook,
        )
        assert result.pattern_frame == "When timelines get tighter, reduce decision load."

    def test_leadership_gap_dominant_returns_leadership_gap_frame(self) -> None:
        """Leadership-gap-dominant → pattern_frame is leadership_gap framing."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="leadership_gap",
            alignment_high=True,
            playbook=playbook,
        )
        assert "dedicated technical owner" in result.pattern_frame

    def test_unknown_dimension_fallback_to_momentum(self) -> None:
        """Unknown dominant_dimension key → fallback to momentum then complexity."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="unknown",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.pattern_frame == "Momentum framing text."

    def test_empty_pattern_frames_returns_empty_string(self) -> None:
        """When pattern_frames is empty, pattern_frame is empty."""
        playbook = _minimal_playbook()
        playbook["pattern_frames"] = {}
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.pattern_frame == ""


class TestStabilityCapSofterCta:
    """When stability_cap_triggered, prefer soft_ctas if present."""

    def test_stability_cap_uses_soft_cta_when_present(self) -> None:
        """stability_cap_triggered and playbook has soft_ctas → use first soft CTA."""
        playbook = _minimal_playbook()
        playbook["soft_ctas"] = ["Just sharing this when you have time.", "No pressure."]
        result = select_outreach_strategy(
            recommendation_type="Soft Value Share",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
            stability_cap_triggered=True,
        )
        assert result.cta_type == "Just sharing this when you have time."

    def test_stability_cap_no_soft_ctas_uses_first_cta(self) -> None:
        """stability_cap_triggered but no soft_ctas → use first CTA."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Soft Value Share",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
            stability_cap_triggered=True,
        )
        assert result.cta_type == "Want me to send that checklist?"

    def test_no_stability_cap_uses_first_cta(self) -> None:
        """stability_cap_triggered=False → use first CTA (ignore soft_ctas for selection)."""
        playbook = _minimal_playbook()
        playbook["soft_ctas"] = ["Soft option."]
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="complexity",
            alignment_high=True,
            playbook=playbook,
            stability_cap_triggered=False,
        )
        assert result.cta_type == "Want me to send that checklist?"


class TestChannelSelection:
    """Channel from playbook channels or default LinkedIn DM."""

    def test_no_channels_default_linkedin_dm(self) -> None:
        """Playbook without channels → default LinkedIn DM."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.channel == "LinkedIn DM"

    def test_empty_channels_default_linkedin_dm(self) -> None:
        """Playbook with empty channels list → default LinkedIn DM."""
        playbook = _minimal_playbook()
        playbook["channels"] = []
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.channel == "LinkedIn DM"

    def test_channels_list_uses_first(self) -> None:
        """Playbook with channels → use first channel."""
        playbook = _minimal_playbook()
        playbook["channels"] = ["Email", "LinkedIn DM"]
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.channel == "Email"


class TestValueAssetByRecommendationType:
    """Value asset: Soft Value Share prefers checklist; else first."""

    def test_soft_value_share_prefers_checklist_asset(self) -> None:
        """Soft Value Share → prefer value asset containing 'checklist'."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Soft Value Share",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert "checklist" in result.value_asset.lower()

    def test_soft_value_share_no_checklist_uses_first(self) -> None:
        """Soft Value Share with no checklist in assets → first asset."""
        playbook = _minimal_playbook()
        playbook["value_assets"] = ["30-minute map", "5 questions"]
        result = select_outreach_strategy(
            recommendation_type="Soft Value Share",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.value_asset == "30-minute map"

    def test_low_pressure_intro_uses_first_asset(self) -> None:
        """Low-Pressure Intro → first value asset."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="complexity",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.value_asset == "2-page Tech Inflection Checklist"

    def test_observe_only_uses_first_asset(self) -> None:
        """Observe Only (selector still returns valid result) → first asset."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Observe Only",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.value_asset == "2-page Tech Inflection Checklist"


class TestRecommendationTypesCoverage:
    """All recommendation types produce valid selector output."""

    @pytest.mark.parametrize(
        "recommendation_type",
        [
            "Observe Only",
            "Soft Value Share",
            "Low-Pressure Intro",
            "Standard Outreach",
            "Direct Strategic Outreach",
        ],
    )
    def test_all_recommendation_types_return_valid_result(self, recommendation_type: str) -> None:
        """Every recommendation_type yields StrategySelectorResult with non-None fields."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type=recommendation_type,
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert isinstance(result, StrategySelectorResult)
        assert isinstance(result.channel, str)
        assert isinstance(result.cta_type, str)
        assert isinstance(result.value_asset, str)
        assert isinstance(result.pattern_frame, str)


class TestMissingPlaybookKeysSafeDefaults:
    """Minimal or missing playbook keys → safe defaults, no KeyError."""

    def test_empty_playbook_safe_defaults(self) -> None:
        """Empty playbook → channel default, empty cta/value_asset/pattern_frame when no lists."""
        result = select_outreach_strategy(
            recommendation_type="Soft Value Share",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook={},
        )
        assert result.channel == "LinkedIn DM"
        assert result.cta_type == ""
        assert result.value_asset == ""
        assert result.pattern_frame == ""

    def test_playbook_none_pattern_frames_safe(self) -> None:
        """playbook with pattern_frames missing (loader may pass None) → empty pattern_frame."""
        playbook = _minimal_playbook()
        playbook["pattern_frames"] = None
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.pattern_frame == ""
        assert result.channel == "LinkedIn DM"
        assert result.cta_type == "Want me to send that checklist?"

    def test_playbook_empty_value_assets_and_ctas(self) -> None:
        """Empty value_assets and ctas → empty strings for cta_type and value_asset."""
        playbook = _minimal_playbook()
        playbook["value_assets"] = []
        playbook["ctas"] = []
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert result.cta_type == ""
        assert result.value_asset == ""

    def test_soft_ctas_non_list_ignored(self) -> None:
        """soft_ctas that is not a list (e.g. string) is ignored; use first CTA."""
        playbook = _minimal_playbook()
        playbook["soft_ctas"] = "not a list"
        result = select_outreach_strategy(
            recommendation_type="Soft Value Share",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
            stability_cap_triggered=True,
        )
        assert result.cta_type == "Want me to send that checklist?"


class TestStrategySelectorResultFrozen:
    """StrategySelectorResult is a frozen dataclass."""

    def test_result_is_frozen(self) -> None:
        """StrategySelectorResult is immutable."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        with pytest.raises(AttributeError):
            result.channel = "Email"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            result.cta_type = "Other"  # type: ignore[misc]


class TestPlaybookImmutability:
    """select_outreach_strategy must not mutate the passed-in playbook dict."""

    def test_playbook_dict_not_mutated(self) -> None:
        """Calling select_outreach_strategy leaves playbook unchanged (no in-place mutation)."""
        playbook = _minimal_playbook()
        snapshot_before = copy.deepcopy(playbook)
        select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension="momentum",
            alignment_high=True,
            playbook=playbook,
        )
        assert playbook == snapshot_before
        assert playbook["pattern_frames"]["momentum"] == "Momentum framing text."


class TestSelectorContractForPipelineIntegration:
    """Contract test: selector output shape and semantics for pipeline (M4) integration.

    When the pipeline wires select_outreach_strategy, it will pass dominant_dimension
    from get_dominant_trs_dimension(snapshot) and playbook from get_ore_playbook.
    These tests assert channel and pattern_frame match that contract.
    """

    def test_selector_output_matches_dominant_dimension_with_loader_constants(self) -> None:
        """With loader-style playbook and dominant=momentum, channel and pattern_frame are set correctly."""
        from app.services.ore.dominant_dimension import get_dominant_trs_dimension
        from app.services.ore.playbook_loader import CTAS, PATTERN_FRAMES, VALUE_ASSETS

        # Playbook shape as produced by get_ore_playbook (no pack or default playbook).
        playbook = {
            "pattern_frames": dict(PATTERN_FRAMES),
            "value_assets": list(VALUE_ASSETS),
            "ctas": list(CTAS),
        }
        dominant = get_dominant_trs_dimension(
            momentum=80,
            complexity=20,
            pressure=10,
            leadership_gap=5,
        )
        assert dominant == "momentum"
        result = select_outreach_strategy(
            recommendation_type="Low-Pressure Intro",
            dominant_dimension=dominant,
            alignment_high=True,
            playbook=playbook,
        )
        assert result.channel == "LinkedIn DM"
        assert result.pattern_frame == PATTERN_FRAMES["momentum"]
        assert result.cta_type == CTAS[0]
        assert result.value_asset == VALUE_ASSETS[0]

    def test_selector_output_pressure_dominant_matches_loader_frame(self) -> None:
        """With loader constants and dominant=pressure, pattern_frame is pressure frame."""
        from app.services.ore.dominant_dimension import get_dominant_trs_dimension
        from app.services.ore.playbook_loader import CTAS, PATTERN_FRAMES, VALUE_ASSETS

        playbook = {
            "pattern_frames": dict(PATTERN_FRAMES),
            "value_assets": list(VALUE_ASSETS),
            "ctas": list(CTAS),
        }
        dominant = get_dominant_trs_dimension(
            momentum=10,
            complexity=20,
            pressure=85,
            leadership_gap=5,
        )
        assert dominant == "pressure"
        result = select_outreach_strategy(
            recommendation_type="Soft Value Share",
            dominant_dimension=dominant,
            alignment_high=True,
            playbook=playbook,
            stability_cap_triggered=True,
        )
        assert result.pattern_frame == PATTERN_FRAMES["pressure"]
        assert result.channel == "LinkedIn DM"


class TestStrategyNotesShapeForAuditPersist:
    """M5 (Issue #117): StrategySelectorResult is serializable to strategy_notes dict for audit persist.

    When M4 persists selector output (Option A), strategy_notes = { channel, cta_type, value_asset,
    pattern_frame }. This contract ensures the selector result can be stored without schema change.
    """

    def test_selector_result_serializable_to_strategy_notes_dict(self) -> None:
        """StrategySelectorResult fields can be persisted as strategy_notes dict for audit."""
        playbook = _minimal_playbook()
        result = select_outreach_strategy(
            recommendation_type="Soft Value Share",
            dominant_dimension="pressure",
            alignment_high=True,
            playbook=playbook,
            stability_cap_triggered=True,
        )
        strategy_notes = {
            "channel": result.channel,
            "cta_type": result.cta_type,
            "value_asset": result.value_asset,
            "pattern_frame": result.pattern_frame,
        }
        assert isinstance(strategy_notes["channel"], str)
        assert isinstance(strategy_notes["cta_type"], str)
        assert isinstance(strategy_notes["value_asset"], str)
        assert isinstance(strategy_notes["pattern_frame"], str)
        assert len(strategy_notes) == 4
