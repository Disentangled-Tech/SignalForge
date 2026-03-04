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
