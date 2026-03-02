"""Diff detection for the monitor (M3): compute unified diff and summary.

Uses stdlib difflib only; no external deps. Summary is a short description
(lines added/removed or excerpt) for LLM and audit.
"""

from __future__ import annotations

import difflib

# Max length for diff_summary field (ChangeEvent)
DIFF_SUMMARY_MAX_LENGTH = 2000


def compute_diff(previous_text: str, current_text: str) -> tuple[str, str]:
    """Compute unified diff and a short summary between two text blobs.

    Args:
        previous_text: Text from the previous snapshot.
        current_text: Text from the current fetch.

    Returns:
        (unified_diff_str, summary_str). unified_diff_str is the result of
        difflib.unified_diff (or empty if no change). summary_str is a
        short human-readable summary (e.g. "3 lines added, 1 removed" or
        "no change"), capped at DIFF_SUMMARY_MAX_LENGTH.
    """
    prev_lines = previous_text.splitlines(keepends=True)
    curr_lines = current_text.splitlines(keepends=True)
    if not prev_lines and not curr_lines:
        return "", "no change"
    if prev_lines == curr_lines:
        return "", "no change"

    unified = "".join(
        difflib.unified_diff(
            prev_lines,
            curr_lines,
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )

    if not unified.strip():
        return "", "no change"

    # Summary: count +/- lines and build short description
    add_count = sum(
        1 for line in unified.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    rem_count = sum(
        1 for line in unified.splitlines() if line.startswith("-") and not line.startswith("---")
    )
    parts = []
    if rem_count:
        parts.append(f"{rem_count} line{'s' if rem_count != 1 else ''} removed")
    if add_count:
        parts.append(f"{add_count} line{'s' if add_count != 1 else ''} added")
    summary = "; ".join(parts) if parts else "content changed"
    if len(summary) > DIFF_SUMMARY_MAX_LENGTH:
        summary = summary[: DIFF_SUMMARY_MAX_LENGTH - 3] + "..."
    return unified, summary
