"""Page snapshot store: save and retrieve latest snapshot by (company_id, url)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.page_snapshot import PageSnapshot


def save_snapshot(
    db: Session,
    company_id: int,
    url: str,
    content_text: str | None,
    content_hash: str,
    fetched_at: datetime,
    source_type: str | None = None,
) -> PageSnapshot:
    """Append a page snapshot. Caller should commit."""
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
    """Return the most recent snapshot for (company_id, url) by fetched_at, or None."""
    stmt = (
        select(PageSnapshot)
        .where(
            PageSnapshot.company_id == company_id,
            PageSnapshot.url == url,
        )
        .order_by(desc(PageSnapshot.fetched_at))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()
