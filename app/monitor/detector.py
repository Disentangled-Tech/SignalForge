"""Diff detector for the monitor (M3): compare current content to latest snapshot.

Given company_id, page_url, and current content, loads the latest snapshot
(via injectable get_latest_snapshot), computes diff; if changed returns
ChangeEvent, else None. Pack-agnostic; no pack_id.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.monitor.diff import compute_diff
from app.schemas.monitor import ChangeEvent, SnapshotLike

# Max snippet length for optional before/after excerpts
SNIPPET_MAX_LEN = 500


def detect_change(
    company_id: int,
    page_url: str,
    current_text: str,
    current_hash: str,
    fetched_at: datetime,
    get_latest_snapshot: Callable[[int, str], SnapshotLike | None],
) -> ChangeEvent | None:
    """Detect if the page content changed since the last snapshot.

    Args:
        company_id: Company ID (for snapshot lookup).
        page_url: Page URL (for snapshot lookup and ChangeEvent).
        current_text: Current page text.
        current_hash: SHA-256 hex digest of current_text.
        fetched_at: When the current content was fetched.
        get_latest_snapshot: Callable(company_id, url) -> SnapshotLike | None.
            Returns the latest snapshot for (company_id, url) or None.

    Returns:
        ChangeEvent if content changed (hash differs and diff is non-empty),
        else None. Returns None when there is no previous snapshot or when
        current_hash equals the previous snapshot's content_hash.
    """
    previous = get_latest_snapshot(company_id, page_url)
    if previous is None:
        return None
    if previous["content_hash"] == current_hash:
        return None

    unified_diff, diff_summary = compute_diff(previous["content_text"], current_text)
    if not unified_diff.strip():
        return None

    snippet_before = previous["content_text"].strip()[:SNIPPET_MAX_LEN] or None
    snippet_after = current_text.strip()[:SNIPPET_MAX_LEN] or None
    if snippet_before and len(previous["content_text"].strip()) > SNIPPET_MAX_LEN:
        snippet_before = snippet_before + "..."
    if snippet_after and len(current_text.strip()) > SNIPPET_MAX_LEN:
        snippet_after = snippet_after + "..."

    return ChangeEvent(
        page_url=page_url,
        timestamp=fetched_at,
        before_hash=previous["content_hash"],
        after_hash=current_hash,
        diff_summary=diff_summary,
        snippet_before=snippet_before or None,
        snippet_after=snippet_after or None,
    )
