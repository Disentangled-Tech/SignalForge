"""Change detection: compare current content to last snapshot (M3, Issue #280)."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.monitor.diff import compute_diff
from app.monitor.schemas import ChangeEvent
from app.monitor.snapshot_store import get_latest_snapshot

logger = logging.getLogger(__name__)

# Snippet length for change event (chars)
SNIPPET_MAX = 500


def _compute_hash(content_text: str) -> str:
    return hashlib.sha256(content_text.encode("utf-8")).hexdigest()


def _truncate_snippet(text: str | None, max_len: int = SNIPPET_MAX) -> str | None:
    if not text:
        return None
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def detect_change(
    db: Session,
    company_id: int,
    url: str,
    current_text: str,
    source_type: str | None = None,
    fetched_at: datetime | None = None,
) -> ChangeEvent | None:
    """If content changed vs last snapshot, return a ChangeEvent; else None."""
    if fetched_at is None:
        fetched_at = datetime.now(UTC)
    current_hash = _compute_hash(current_text)
    previous = get_latest_snapshot(db, company_id, url)
    if previous is None:
        return None
    if previous.content_hash == current_hash:
        return None
    previous_text = previous.content_text or ""
    unified, summary = compute_diff(previous_text, current_text)
    return ChangeEvent(
        page_url=url,
        timestamp=fetched_at,
        before_hash=previous.content_hash,
        after_hash=current_hash,
        diff_summary=summary,
        snippet_before=_truncate_snippet(previous_text),
        snippet_after=_truncate_snippet(current_text),
        company_id=company_id,
        source_type=source_type,
    )
