"""ORE strategy selector — deterministic channel, CTA, value asset, pattern frame (Issue #117 M2).

Pure function: no LLM, no DB, no network. Chooses strategy from recommendation_type,
dominant TRS dimension, alignment, and playbook. Used by ore_pipeline (M4) after
policy gate and dominant-dimension computation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Fallback order for pattern_frame when dominant dimension key is missing (plan: momentum then complexity).
_PATTERN_FRAME_FALLBACK_ORDER = ("momentum", "complexity")
_DEFAULT_CHANNEL = "LinkedIn DM"


@dataclass(frozen=True)
class StrategySelectorResult:
    """Result of deterministic strategy selection for ORE draft generation."""

    channel: str
    cta_type: str
    value_asset: str
    pattern_frame: str


def select_outreach_strategy(
    recommendation_type: str,
    dominant_dimension: str,
    alignment_high: bool,
    playbook: dict[str, Any],
    *,
    stability_cap_triggered: bool = False,
) -> StrategySelectorResult:
    """Choose channel, CTA, value asset, and pattern frame from gate + playbook.

    Args:
        recommendation_type: From policy gate (e.g. "Soft Value Share", "Low-Pressure Intro").
        dominant_dimension: From get_dominant_trs_dimension (e.g. "momentum", "pressure").
        alignment_high: Alignment flag from ESL context. Reserved for future use (e.g. channel or
            CTA rules by alignment); not used in selection logic until M4+.
        playbook: Normalized ORE playbook (pattern_frames, value_assets, ctas; optional channels, soft_ctas).
        stability_cap_triggered: When True, prefer softer CTA (soft_ctas if present, else first CTA).

    Returns:
        StrategySelectorResult with channel, cta_type, value_asset, pattern_frame.
    """
    pattern_frames = playbook.get("pattern_frames") or {}
    value_assets = playbook.get("value_assets") or []
    ctas = playbook.get("ctas") or []
    channels = playbook.get("channels")
    soft_ctas = playbook.get("soft_ctas") if isinstance(playbook.get("soft_ctas"), list) else None

    pattern_frame = _resolve_pattern_frame(pattern_frames, dominant_dimension)
    channel = _resolve_channel(channels)
    cta_type = _resolve_cta(ctas, soft_ctas, stability_cap_triggered)
    value_asset = _resolve_value_asset(value_assets, recommendation_type)

    return StrategySelectorResult(
        channel=channel,
        cta_type=cta_type,
        value_asset=value_asset,
        pattern_frame=pattern_frame,
    )


def _resolve_pattern_frame(pattern_frames: dict[str, str], dominant_dimension: str) -> str:
    """Resolve pattern_frame by dominant dimension with fallback (momentum then complexity)."""
    if dominant_dimension and dominant_dimension in pattern_frames:
        return pattern_frames[dominant_dimension]
    for fallback in _PATTERN_FRAME_FALLBACK_ORDER:
        if fallback in pattern_frames:
            return pattern_frames[fallback]
    return ""


def _resolve_channel(channels: Any) -> str:
    """Resolve channel: first from playbook channels list, else default LinkedIn DM."""
    if isinstance(channels, list) and len(channels) > 0 and isinstance(channels[0], str):
        return str(channels[0]).strip() or _DEFAULT_CHANNEL
    return _DEFAULT_CHANNEL


def _resolve_cta(
    ctas: list[Any],
    soft_ctas: list[Any] | None,
    stability_cap_triggered: bool,
) -> str:
    """Resolve CTA: when stability cap triggered, prefer first soft_cta else first cta; else first cta."""
    if stability_cap_triggered and soft_ctas and len(soft_ctas) > 0:
        item = soft_ctas[0]
        return str(item).strip() if item is not None else ""
    if ctas and len(ctas) > 0:
        item = ctas[0]
        return str(item).strip() if item is not None else ""
    return ""


def _resolve_value_asset(value_assets: list[Any], recommendation_type: str) -> str:
    """Resolve value asset: Soft Value Share prefers first or checklist-like; else first."""
    if not value_assets:
        return ""
    if recommendation_type == "Soft Value Share":
        for asset in value_assets:
            s = str(asset).strip() if asset is not None else ""
            if s and "checklist" in s.lower():
                return s
    return str(value_assets[0]).strip() if value_assets[0] is not None else ""
