"""Unit tests for ORE playbook schema contract (Issue #176 M1)."""

from __future__ import annotations

from app.services.ore.playbook_schema import ORE_PLAYBOOK_OPTIONAL_KEYS, OREPlaybook


class TestOREPlaybookSchema:
    """ORE playbook TypedDict and optional keys constant."""

    def test_optional_keys_defined(self) -> None:
        """ORE_PLAYBOOK_OPTIONAL_KEYS contains expected optional keys (M1 includes sensitivity_levels)."""
        assert ORE_PLAYBOOK_OPTIONAL_KEYS == frozenset(
            {
                "opening_templates",
                "value_statements",
                "forbidden_phrases",
                "tone",
                "sensitivity_levels",
            }
        )

    def test_ore_playbook_minimal_shape(self) -> None:
        """OREPlaybook accepts minimal dict (pattern_frames, value_assets, ctas)."""
        minimal: OREPlaybook = {
            "pattern_frames": {"momentum": "text"},
            "value_assets": ["asset1"],
            "ctas": ["CTA1"],
        }
        assert minimal["pattern_frames"]["momentum"] == "text"
        assert minimal["value_assets"] == ["asset1"]
        assert minimal["ctas"] == ["CTA1"]

    def test_ore_playbook_with_optional_keys(self) -> None:
        """OREPlaybook accepts all optional keys."""
        full: OREPlaybook = {
            "pattern_frames": {"momentum": "text"},
            "value_assets": ["a"],
            "ctas": ["c"],
            "opening_templates": ["Hi {{name}},"],
            "value_statements": ["We help teams."],
            "forbidden_phrases": ["I saw you"],
            "tone": "professional",
        }
        assert full["forbidden_phrases"] == ["I saw you"]
        assert full["tone"] == "professional"

    def test_ore_playbook_tone_dict(self) -> None:
        """OREPlaybook accepts tone as dict."""
        with_tone_map: OREPlaybook = {
            "pattern_frames": {},
            "value_assets": [],
            "ctas": [],
            "tone": {"default": "warm", "Soft Value Share": "gentle"},
        }
        assert isinstance(with_tone_map["tone"], dict)
