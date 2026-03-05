"""Unit tests for ORE playbook loader (Issue #176 M2)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.ore.playbook_loader import (
    CTAS,
    DEFAULT_PLAYBOOK_NAME,
    PATTERN_FRAMES,
    VALUE_ASSETS,
    get_ore_playbook,
)


class TestPlaybookLoaderFallbacks:
    """get_ore_playbook with pack None or missing playbook returns normalized defaults."""

    def test_pack_none_returns_module_constants(self) -> None:
        """get_ore_playbook(None) returns pattern_frames, value_assets, ctas from constants."""
        playbook = get_ore_playbook(None)
        assert playbook["pattern_frames"] == PATTERN_FRAMES
        assert playbook["value_assets"] == VALUE_ASSETS
        assert playbook["ctas"] == CTAS
        assert playbook.get("sensitivity_levels") is None

    def test_pack_none_default_playbook_name(self) -> None:
        """get_ore_playbook(None) uses default playbook name internally."""
        playbook = get_ore_playbook(None, playbook_name=DEFAULT_PLAYBOOK_NAME)
        assert playbook["pattern_frames"] == PATTERN_FRAMES

    def test_pack_without_playbook_returns_constants(self) -> None:
        """When pack has no ore_outreach key, returns module constants."""
        pack = MagicMock()
        pack.playbooks = {}
        playbook = get_ore_playbook(pack)
        assert playbook["pattern_frames"] == PATTERN_FRAMES
        assert playbook["value_assets"] == VALUE_ASSETS
        assert playbook["ctas"] == CTAS

    def test_pack_with_empty_playbook_returns_constants(self) -> None:
        """When pack has ore_outreach but it is empty dict, returns constants."""
        pack = MagicMock()
        pack.playbooks = {"ore_outreach": {}}
        playbook = get_ore_playbook(pack)
        assert playbook["pattern_frames"] == PATTERN_FRAMES
        assert playbook["value_assets"] == VALUE_ASSETS
        assert playbook["ctas"] == CTAS


class TestPlaybookLoaderFromPack:
    """get_ore_playbook with pack containing full or partial playbook."""

    def test_pack_with_full_playbook_returns_pack_values(self) -> None:
        """When pack has full ore_outreach, returned playbook uses pack values."""
        custom_frames = {"momentum": "Custom momentum text.", "complexity": "Custom complexity."}
        custom_assets = ["Custom asset 1"]
        custom_ctas = ["Custom CTA"]
        pack = MagicMock()
        pack.playbooks = {
            "ore_outreach": {
                "pattern_frames": custom_frames,
                "value_assets": custom_assets,
                "ctas": custom_ctas,
            }
        }
        playbook = get_ore_playbook(pack)
        assert playbook["pattern_frames"] == custom_frames
        assert playbook["value_assets"] == custom_assets
        assert playbook["ctas"] == custom_ctas

    def test_pack_with_partial_playbook_fills_missing_from_constants(self) -> None:
        """When pack has only some keys, missing keys use constants."""
        custom_frames = {"momentum": "Only momentum"}
        pack = MagicMock()
        pack.playbooks = {"ore_outreach": {"pattern_frames": custom_frames}}
        playbook = get_ore_playbook(pack)
        assert playbook["pattern_frames"] == custom_frames
        assert playbook["value_assets"] == VALUE_ASSETS
        assert playbook["ctas"] == CTAS

    def test_pack_sensitivity_levels_passthrough(self) -> None:
        """When playbook has sensitivity_levels list, it is returned as-is."""
        pack = MagicMock()
        pack.playbooks = {
            "ore_outreach": {
                "pattern_frames": {"momentum": "m"},
                "value_assets": ["v"],
                "ctas": ["c"],
                "sensitivity_levels": ["low", "medium"],
            }
        }
        playbook = get_ore_playbook(pack)
        assert playbook["sensitivity_levels"] == ["low", "medium"]

    def test_playbook_name_parameter(self) -> None:
        """Different playbook_name loads different playbook from pack."""
        pack = MagicMock()
        pack.playbooks = {
            "ore_outreach": {"pattern_frames": {"momentum": "default"}},
            "other_playbook": {"pattern_frames": {"momentum": "other"}},
        }
        default_playbook = get_ore_playbook(pack, playbook_name="ore_outreach")
        other_playbook = get_ore_playbook(pack, playbook_name="other_playbook")
        assert default_playbook["pattern_frames"]["momentum"] == "default"
        assert other_playbook["pattern_frames"]["momentum"] == "other"

    def test_enable_ore_polish_default_false(self) -> None:
        """When enable_ore_polish is missing, normalized playbook has enable_ore_polish False (Issue #119)."""
        pack = MagicMock()
        pack.playbooks = {"ore_outreach": {"pattern_frames": {"momentum": "m"}}}
        playbook = get_ore_playbook(pack)
        assert playbook.get("enable_ore_polish") is False

    def test_enable_ore_polish_true_when_bool_or_truthy_string(self) -> None:
        """enable_ore_polish True, 'true', or 'yes' (case-insensitive) normalize to True (Issue #119)."""
        pack = MagicMock()
        pack.playbooks = {
            "ore_outreach": {
                "pattern_frames": {"momentum": "m"},
                "enable_ore_polish": True,
            }
        }
        playbook = get_ore_playbook(pack)
        assert playbook.get("enable_ore_polish") is True
        pack.playbooks["ore_outreach"]["enable_ore_polish"] = "true"
        playbook = get_ore_playbook(pack)
        assert playbook.get("enable_ore_polish") is True
        pack.playbooks["ore_outreach"]["enable_ore_polish"] = "yes"
        playbook = get_ore_playbook(pack)
        assert playbook.get("enable_ore_polish") is True

    def test_enable_ore_polish_false_when_false_or_no(self) -> None:
        """enable_ore_polish False or 'no' yields False (Issue #119)."""
        pack = MagicMock()
        pack.playbooks = {
            "ore_outreach": {"pattern_frames": {"momentum": "m"}, "enable_ore_polish": False}
        }
        assert get_ore_playbook(pack).get("enable_ore_polish") is False
        pack.playbooks["ore_outreach"]["enable_ore_polish"] = "no"
        assert get_ore_playbook(pack).get("enable_ore_polish") is False

    def test_channel_passthrough_when_string(self) -> None:
        """When playbook has channel (non-empty string), normalized playbook includes it (Issue #121 M4)."""
        pack = MagicMock()
        pack.playbooks = {
            "ore_outreach": {
                "pattern_frames": {"momentum": "m"},
                "value_assets": ["v"],
                "ctas": ["c"],
                "channel": "Email",
            }
        }
        playbook = get_ore_playbook(pack)
        assert playbook.get("channel") == "Email"

    def test_channel_none_when_missing(self) -> None:
        """When playbook has no channel, normalized playbook has channel None (Issue #121 M4)."""
        pack = MagicMock()
        pack.playbooks = {"ore_outreach": {"pattern_frames": {"momentum": "m"}}}
        playbook = get_ore_playbook(pack)
        assert playbook.get("channel") is None

    def test_channel_none_when_empty_string(self) -> None:
        """When playbook channel is empty or whitespace, normalized playbook has channel None (Issue #121 M4)."""
        pack = MagicMock()
        pack.playbooks = {
            "ore_outreach": {
                "pattern_frames": {"momentum": "m"},
                "channel": "",
            }
        }
        playbook = get_ore_playbook(pack)
        assert playbook.get("channel") is None

        pack.playbooks["ore_outreach"]["channel"] = "   "
        playbook = get_ore_playbook(pack)
        assert playbook.get("channel") is None

    def test_explainability_snippet_template_passthrough_when_non_empty(self) -> None:
        """When playbook has explainability_snippet_template (non-empty string), it is normalized (Issue #121 M5)."""
        pack = MagicMock()
        pack.playbooks = {
            "ore_outreach": {
                "pattern_frames": {"momentum": "m"},
                "value_assets": ["v"],
                "ctas": ["c"],
                "explainability_snippet_template": "Key drivers: {{TOP_SIGNALS}}. Use for framing only.",
            }
        }
        playbook = get_ore_playbook(pack)
        assert playbook.get("explainability_snippet_template") == (
            "Key drivers: {{TOP_SIGNALS}}. Use for framing only."
        )

    def test_explainability_snippet_template_none_when_missing(self) -> None:
        """When playbook has no explainability_snippet_template, normalized playbook has it None (Issue #121 M5)."""
        pack = MagicMock()
        pack.playbooks = {"ore_outreach": {"pattern_frames": {"momentum": "m"}}}
        playbook = get_ore_playbook(pack)
        assert playbook.get("explainability_snippet_template") is None

    def test_explainability_snippet_template_none_when_empty_string(self) -> None:
        """When explainability_snippet_template is empty or whitespace, normalized playbook has it None (Issue #121 M5)."""
        pack = MagicMock()
        pack.playbooks = {
            "ore_outreach": {
                "pattern_frames": {"momentum": "m"},
                "explainability_snippet_template": "",
            }
        }
        playbook = get_ore_playbook(pack)
        assert playbook.get("explainability_snippet_template") is None

        pack.playbooks["ore_outreach"]["explainability_snippet_template"] = "   "
        playbook = get_ore_playbook(pack)
        assert playbook.get("explainability_snippet_template") is None
