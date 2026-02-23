"""Ingestion orchestrator: adapter -> normalize -> resolve -> store (Issue #89)."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.ingestion.base import SourceAdapter
from app.ingestion.event_storage import store_signal_event
from app.ingestion.normalize import normalize_raw_event
from app.services.company_resolver import resolve_or_create_company
from app.services.pack_resolver import get_default_pack_id, resolve_pack

logger = logging.getLogger(__name__)


def run_ingest(
    db: Session,
    adapter: SourceAdapter,
    since: datetime,
) -> dict:
    """Run ingestion for an adapter.

    Fetches raw events, normalizes, resolves companies, and stores signal events.
    One event failure does not stop the run (per PRD).

    Returns
    -------
    dict
        {inserted: int, skipped_duplicate: int, skipped_invalid: int, errors: list}
    """
    inserted = 0
    skipped_duplicate = 0
    skipped_invalid = 0
    errors: list[str] = []

    raw_events = adapter.fetch_events(since)
    source = adapter.source_name
    pack_id = get_default_pack_id(db)
    pack = resolve_pack(db, pack_id) if pack_id else None

    for raw in raw_events:
        try:
            normalized = normalize_raw_event(raw, source, pack=pack)
            if normalized is None:
                skipped_invalid += 1
                continue

            event_data, company_create = normalized
            company, _ = resolve_or_create_company(db, company_create)
            event_data["company_id"] = company.id
            event_data["pack_id"] = pack_id

            result = store_signal_event(db, **event_data)
            if result is None:
                skipped_duplicate += 1
            else:
                inserted += 1
        except Exception as e:
            errors.append(f"{source}:{getattr(raw, 'source_event_id', '?')}: {e}")
            logger.exception("Ingest failed for event: %s", raw)

    return {
        "inserted": inserted,
        "skipped_duplicate": skipped_duplicate,
        "skipped_invalid": skipped_invalid,
        "errors": errors,
    }
