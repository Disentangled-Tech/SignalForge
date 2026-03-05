"""Unit tests for ORE outreach template library (Issue #118 M2)."""

from __future__ import annotations

import pytest

from app.services.ore.outreach_templates import (
    CHANNELS,
    OUTREACH_TYPES,
    get_template,
)

# Required placeholders per docs/outreach-template-library.md
_REQUIRED_PLACEHOLDERS = frozenset(
    {"{founder_name}", "{company_name}", "{pattern_frame}", "{value_asset}", "{cta}"}
)

# Opt-out phrases that must appear in at least one form per template
_OPT_OUT_PHRASES = (
    "no pressure",
    "no worries",
    "completely understand",
    "completely fine",
    "if now isn't",
    "just offering",
)


class TestGetTemplateReturnsContent:
    """get_template returns non-empty string for each (outreach_type, channel) pair."""

    @pytest.mark.parametrize("outreach_type", OUTREACH_TYPES)
    @pytest.mark.parametrize("channel", CHANNELS)
    def test_get_template_returns_non_empty(self, outreach_type: str, channel: str) -> None:
        """Every (type, channel) pair has a template."""
        content = get_template(outreach_type, channel)
        assert content is not None
        assert isinstance(content, str)
        assert len(content.strip()) > 0

    def test_all_eight_combinations_covered(self) -> None:
        """Exactly 4 types × 2 channels = 8 templates."""
        count = 0
        for outreach_type in OUTREACH_TYPES:
            for channel in CHANNELS:
                if get_template(outreach_type, channel) is not None:
                    count += 1
        assert count == 8


class TestGetTemplateUnknownInputs:
    """get_template returns None for unknown outreach_type or channel."""

    def test_unknown_outreach_type_returns_none(self) -> None:
        """Unknown outreach_type returns None."""
        assert get_template("Observe Only", "DM") is None
        assert get_template("Unknown Type", "Email") is None

    def test_unknown_channel_returns_none(self) -> None:
        """Unknown channel returns None."""
        assert get_template("Soft Value Share", "SMS") is None
        assert get_template("Soft Value Share", "LinkedIn DM") is None
        assert get_template("Soft Value Share", "") is None


class TestTemplateContentContract:
    """Templates satisfy placeholder and opt-out contract (Issue #118)."""

    @pytest.mark.parametrize("outreach_type", OUTREACH_TYPES)
    @pytest.mark.parametrize("channel", CHANNELS)
    def test_template_contains_required_placeholders(
        self, outreach_type: str, channel: str
    ) -> None:
        """Each template contains all five required placeholders."""
        content = get_template(outreach_type, channel)
        assert content is not None
        for placeholder in _REQUIRED_PLACEHOLDERS:
            assert placeholder in content, (
                f"Template {outreach_type}/{channel} missing placeholder {placeholder}"
            )

    @pytest.mark.parametrize("outreach_type", OUTREACH_TYPES)
    @pytest.mark.parametrize("channel", CHANNELS)
    def test_template_contains_opt_out_language(self, outreach_type: str, channel: str) -> None:
        """Each template contains opt-out language (critic requirement)."""
        content = get_template(outreach_type, channel)
        assert content is not None
        lower = content.lower()
        assert any(phrase in lower for phrase in _OPT_OUT_PHRASES), (
            f"Template {outreach_type}/{channel} must include opt-out language"
        )


class TestConstants:
    """Module constants match expected outreach types and channels."""

    def test_outreach_types_four_draft_types(self) -> None:
        """OUTREACH_TYPES has exactly the four draft-producing types."""
        assert OUTREACH_TYPES == (
            "Soft Value Share",
            "Low-Pressure Intro",
            "Standard Outreach",
            "Direct Strategic Outreach",
        )

    def test_channels_dm_and_email(self) -> None:
        """CHANNELS is DM and Email."""
        assert CHANNELS == ("DM", "Email")
