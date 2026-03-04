"""ORE playbook loader — single source of truth for normalized ORE playbook (Issue #176 M2).

Given a Pack and playbook name, returns a normalized ORE playbook dict with defaults
for missing keys. Used by draft_generator and ore_pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.packs.loader import Pack

# Default playbook name used by ORE pipeline (plan: single playbook per ORE run).
DEFAULT_PLAYBOOK_NAME = "ore_outreach"

# Pattern frames (generic, non-invasive) per ORE design spec §6.
# Fallback when pack not provided or playbook missing (Phase 2, Step 3.5).
PATTERN_FRAMES = {
    "momentum": "When a team's pace picks up, tech decisions that worked earlier can start costing more.",
    "complexity": "When products add integrations/AI/enterprise asks, systems often need a stabilization pass.",
    "pressure": "When timelines get tighter, it helps to reduce decision load and get a clean plan.",
    "leadership_gap": "When there isn't a dedicated technical owner yet, teams often benefit from a short-term systems guide.",
}

VALUE_ASSETS = [
    "2-page Tech Inflection Checklist",
    "30-minute 'what's breaking next' map",
    "5 questions to reduce tech chaos",
]

CTAS = [
    "Want me to send that checklist?",
    "Open to a 15-min compare-notes call?",
    "If helpful, I can share a one-page approach—want it?",
]


def get_ore_playbook(
    pack: Pack | None, playbook_name: str = DEFAULT_PLAYBOOK_NAME
) -> dict[str, Any]:
    """Return normalized ORE playbook: pattern_frames, value_assets, ctas, optional keys.

    When pack is None or playbook is missing, uses module constants and defaults.
    Optional keys (opening_templates, value_statements, forbidden_phrases, tone,
    sensitivity_levels) default to empty list or None for M3+ compatibility.

    Returns:
        Dict with at least: pattern_frames, value_assets, ctas, sensitivity_levels.
    """
    if pack is None:
        return _normalize_playbook({}, playbook_name)

    raw = pack.playbooks.get(playbook_name) or {}
    return _normalize_playbook(raw, playbook_name)


def _enable_ore_polish_from_raw(value: Any) -> bool:
    """Normalize enable_ore_polish from YAML: True, or string 'true'/'yes' (case-insensitive) → True; else False."""
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in ("true", "yes"):
        return True
    return False


def _normalize_playbook(raw: dict[str, Any], _playbook_name: str) -> dict[str, Any]:
    """Fill required and optional keys with defaults when missing (Issue #176 M3)."""
    forbidden = raw.get("forbidden_phrases")
    if not isinstance(forbidden, list):
        forbidden = []
    else:
        forbidden = [str(p).strip() for p in forbidden if isinstance(p, str) and str(p).strip()]

    return {
        "pattern_frames": raw.get("pattern_frames") or PATTERN_FRAMES,
        "value_assets": raw.get("value_assets") or VALUE_ASSETS,
        "ctas": raw.get("ctas") or CTAS,
        "sensitivity_levels": raw.get("sensitivity_levels")
        if isinstance(raw.get("sensitivity_levels"), list)
        else None,
        "forbidden_phrases": forbidden,
        "opening_templates": raw.get("opening_templates")
        if isinstance(raw.get("opening_templates"), list)
        else [],
        "value_statements": raw.get("value_statements")
        if isinstance(raw.get("value_statements"), list)
        else [],
        "tone": raw.get("tone") if isinstance(raw.get("tone"), (str, dict)) else None,
        "channel": (
            raw.get("channel").strip()
            if isinstance(raw.get("channel"), str) and raw.get("channel", "").strip()
            else None
        ),
        "enable_ore_polish": _enable_ore_polish_from_raw(raw.get("enable_ore_polish")),
    }
