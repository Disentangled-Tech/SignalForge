"""Store SignalEvents with deduplication (Issue #89)."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.signal_event import SignalEvent

logger = logging.getLogger(__name__)


def store_signal_event(
    db: Session,
    *,
    company_id: int | None,
    source: str,
    source_event_id: str | None,
    event_type: str,
    event_time: datetime,
    title: str | None = None,
    summary: str | None = None,
    url: str | None = None,
    raw: dict | None = None,
    confidence: float | None = 0.7,
    pack_id: UUID | None = None,
) -> SignalEvent | None:
    """Store a signal event with deduplication.

    If source_event_id is not None and an event with the same (source, source_event_id)
    already exists, returns None without inserting. Otherwise inserts and returns the
    new SignalEvent.

    Parameters
    ----------
    db : Session
        SQLAlchemy session (caller manages transaction).
    company_id : int | None
        FK to companies.id (nullable until resolved).
    source : str
        Adapter identifier (e.g. 'crunchbase', 'producthunt').
    source_event_id : str | None
        Upstream event ID for deduplication.
    event_type : str
        Canonical event type from taxonomy.
    event_time : datetime
        When the event occurred.
    title, summary, url, raw, confidence : optional
        Additional event fields.
    pack_id : UUID | None
        Signal pack UUID (Issue #189). When None, event is legacy/unassigned.

    Returns
    -------
    SignalEvent | None
        The new record, or None if duplicate.
    """
    if source_event_id is not None and source_event_id.strip():
        existing = (
            db.query(SignalEvent)
            .filter(
                SignalEvent.source == source,
                SignalEvent.source_event_id == source_event_id,
            )
            .first()
        )
        if existing is not None:
            logger.debug(
                "Duplicate signal event skipped: source=%s source_event_id=%s",
                source,
                source_event_id,
            )
            return None

    event = SignalEvent(
        company_id=company_id,
        source=source,
        source_event_id=(source_event_id.strip() or None) if source_event_id else None,
        event_type=event_type,
        event_time=event_time,
        title=title,
        summary=summary,
        url=url,
        raw=raw,
        confidence=confidence,
        pack_id=pack_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
