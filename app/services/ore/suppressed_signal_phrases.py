"""Core reference phrases for suppressed signals (Issue #120 M2).

Maps signal_id → phrases that would "reference" that signal in a draft.
Used by the critic when suppressed_signal_ids is non-empty: draft must not
contain these phrases (case-insensitive). Only includes signal IDs that can
appear in CORE_BAN_SIGNAL_IDS or pack blocked_signals / prohibited_combinations.
Unknown signal_ids return empty list.
"""

from __future__ import annotations

# Phrases that would reference the signal in outreach copy (distress/financial).
# Extend when adding core-banned or commonly blocked signals; see CORE_BAN_SIGNAL_IDS.md.
_SUPPRESSED_SIGNAL_PHRASES: dict[str, list[str]] = {
    "financial_distress": [
        "financial trouble",
        "struggling financially",
        "falling behind",
        "in distress",
        "financial distress",
        "cash flow crisis",
        "running out of runway",
        "burn rate",
    ],
    "distress_mentioned": [
        "in distress",
        "distress",
        "crisis",
        "struggling",
    ],
    "bankruptcy_filed": [
        "bankruptcy",
        "filed for bankruptcy",
    ],
}


def get_phrases_for_suppressed_signals(signal_ids: set[str]) -> dict[str, list[str]]:
    """Return reference phrases per signal_id for the given set.

    Only known signal_ids (in core phrase map) get non-empty lists.
    Unknown signal_ids are omitted or get empty list so critic does not fail.

    Args:
        signal_ids: Set of signal_ids that must not be referenced in the draft.

    Returns:
        Dict mapping each known signal_id to its list of reference phrases.
    """
    if not signal_ids:
        return {}
    result: dict[str, list[str]] = {}
    for sid in signal_ids:
        phrases = _SUPPRESSED_SIGNAL_PHRASES.get(sid)
        if phrases:
            result[sid] = list(phrases)
    return result
