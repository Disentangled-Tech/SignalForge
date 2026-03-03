"""Page snapshot storage for monitor (M2, Issue #280)."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.page_snapshot import PageSnapshot

logger = logging.getLogger(__name__)


def _compute_hash(content_text: str) -> str:
    """SHA-256 hex digest of content text."""
    return hashlib.sha256(content_text.encode("utf-8")).hexdigest()


def save_snapshot(
    db: Session,
    company_id: int,
    url: str,
    content_text: str | None,
    content_hash: str | None = None,
    fetched_at: datetime | None = None,
    source_type: str | None = None,
) -> PageSnapshot:
    """Save or update snapshot for (company_id, url). Latest wins."""
    if content_hash is None:
        content_hash = _compute_hash(content_text or "")
    if fetched_at is None:
        fetched_at = datetime.now(UTC)
    existing = (
        db.query(PageSnapshot)
        .filter(
            PageSnapshot.company_id == company_id,
            PageSnapshot.url == url,
        )
        .first()
    )
    if existing:
        existing.content_hash = content_hash
        existing.content_text = content_text
        existing.fetched_at = fetched_at
        existing.source_type = source_type
        db.flush()
        db.refresh(existing)
        return existing
    row = PageSnapshot(
        company_id=company_id,
        url=url,
        content_hash=content_hash,
        content_text=content_text,
        fetched_at=fetched_at,
        source_type=source_type,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return row


def get_latest_snapshot(
    db: Session,
    company_id: int,
    url: str,
) -> PageSnapshot | None:
    """Return the latest snapshot for (company_id, url), or None."""
    return (
        db.query(PageSnapshot)
        .filter(
            PageSnapshot.company_id == company_id,
            PageSnapshot.url == url,
        )
        .first()
    )
