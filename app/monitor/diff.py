"""Diff computation for monitor (M3, Issue #280)."""

from __future__ import annotations

import difflib


def compute_diff(previous_text: str, current_text: str) -> tuple[str, str]:
    """Compute unified diff and a short summary.

    Returns (unified_diff_string, summary). Summary is a short line-based
    summary (e.g. "N lines added, M removed") or first N chars of diff.
    Uses difflib only; no external deps.
    """
    prev_lines = (previous_text or "").splitlines(keepends=True)
    curr_lines = (current_text or "").splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            prev_lines,
            curr_lines,
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )
    unified = "".join(diff_lines)

    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    summary = f"{added} lines added, {removed} removed"
    if len(unified) > 500:
        summary += f"; diff length {len(unified)} chars"
    return unified, summary
