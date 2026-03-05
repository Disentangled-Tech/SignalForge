"""Parameterized outreach template library for ORE (Issue #118).

Central store of message templates keyed by (outreach_type, channel).
Templates use placeholders: {founder_name}, {company_name}, {pattern_frame},
{value_asset}, {cta}. Each template includes opt-out language.
No resolution in this module — data access only (get_template).

TODO M5: Wire fallback to template library — in _build_critic_compliant_fallback
(or regenerate path), call resolve_template(recommendation_type, channel, ...)
when template exists; keep legacy fallback otherwise. See implementation plan M5.
"""

from __future__ import annotations

from pathlib import Path

# Outreach types (ESL recommendation types that produce a draft; Observe Only has no template).
OUTREACH_TYPES: tuple[str, ...] = (
    "Soft Value Share",
    "Low-Pressure Intro",
    "Standard Outreach",
    "Direct Strategic Outreach",
)

# Channels for template selection.
CHANNELS: tuple[str, ...] = ("DM", "Email")

# Map display name -> file key (lowercase, underscores).
_OUTREACH_TYPE_TO_KEY: dict[str, str] = {
    "Soft Value Share": "soft_value_share",
    "Low-Pressure Intro": "low_pressure_intro",
    "Standard Outreach": "standard_outreach",
    "Direct Strategic Outreach": "direct_strategic_outreach",
}

_CHANNEL_TO_KEY: dict[str, str] = {
    "DM": "dm",
    "Email": "email",
}


def _templates_dir() -> Path:
    """Return path to app/prompts/ore_templates (relative to this module under app/services/ore)."""
    app_dir = Path(__file__).resolve().parent.parent.parent
    return app_dir / "prompts" / "ore_templates"


def get_template(outreach_type: str, channel: str) -> str | None:
    """Return raw template body for (outreach_type, channel), or None if unknown/missing.

    Args:
        outreach_type: One of OUTREACH_TYPES (e.g. "Soft Value Share").
        channel: One of CHANNELS (e.g. "DM", "Email").

    Returns:
        Template string with placeholders intact, or None if type/channel unknown or file missing.
    """
    type_key = _OUTREACH_TYPE_TO_KEY.get(outreach_type)
    channel_key = _CHANNEL_TO_KEY.get(channel)
    if type_key is None or channel_key is None:
        return None
    path = _templates_dir() / f"{type_key}_{channel_key}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip()
