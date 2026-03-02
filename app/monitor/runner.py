"""Monitor runner: fetch → snapshot → diff → collect ChangeEvents (M4, Issue #280).

M6: run_monitor_full runs the full pipeline and persists Core Event candidates
as SignalEvents with source='page_monitor' and deterministic source_event_id.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from urllib.parse import urljoin
from uuid import UUID

from sqlalchemy.orm import Session

from app.ingestion.event_storage import store_signal_event
from app.models.company import Company
from app.monitor.detector import detect_change
from app.monitor.interpretation import interpret_change_event
from app.monitor.schemas import ChangeEvent
from app.monitor.snapshot_store import save_snapshot
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.schemas.core_events import CoreEventCandidate
from app.services.extractor import extract_text
from app.services.fetcher import fetch_page
from app.services.pack_resolver import get_pack_for_workspace

logger = logging.getLogger(__name__)

# Source identifier for monitor-origin SignalEvents (plan M6)
PAGE_MONITOR_SOURCE = "page_monitor"

# URL paths to monitor (plan: blog, careers, press, pricing, docs/changelog)
MONITOR_PATHS = ["/blog", "/careers", "/press", "/pricing", "/docs/changelog"]


def _normalize_base_url(url: str) -> str:
    """Strip trailing slash, ensure scheme."""
    url = (url or "").strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _urls_to_monitor(base_url: str) -> list[tuple[str, str | None]]:
    """Return list of (url, source_type) for monitor scope (homepage + MONITOR_PATHS)."""
    base = _normalize_base_url(base_url)
    out: list[tuple[str, str | None]] = [(base, "homepage")]
    for path in MONITOR_PATHS:
        p = path.strip("/")
        source_type = p.replace("/", "_") if p else "homepage"
        full_url = urljoin(base + "/", path)
        out.append((full_url, source_type))
    return out


async def run_monitor(
    db: Session,
    company_ids: list[int] | None = None,
) -> list[ChangeEvent]:
    """Run the diff-based monitor and return structured change events.

    For each company with website_url (or in company_ids), fetches each URL
    in scope (homepage, blog, careers, press, pricing, docs/changelog) with
    robots-aware fetch, saves snapshot, detects diff vs previous snapshot,
    and collects ChangeEvents. No LLM; caller may pass events to interpretation later.

    Parameters
    ----------
    db : Session
        Active database session (caller manages transaction).
    company_ids : list[int] | None
        If provided, only these companies; else all with website_url.

    Returns
    -------
    list[ChangeEvent]
        All change events from this run (in-memory only; not persisted to a table).
    """
    if company_ids is not None:
        companies = (
            db.query(Company)
            .filter(Company.id.in_(company_ids), Company.website_url.isnot(None))
            .all()
        )
    else:
        companies = db.query(Company).filter(Company.website_url.isnot(None)).all()

    events: list[ChangeEvent] = []
    for company in companies:
        base_url = (company.website_url or "").strip()
        if not base_url:
            continue
        base_url = _normalize_base_url(base_url)
        for page_url, source_type in _urls_to_monitor(base_url):
            html = await fetch_page(page_url, check_robots=True)
            if not html:
                continue
            text = extract_text(html)
            if len(text) < 100:
                continue
            fetched_at = datetime.now(UTC)
            change_ev = detect_change(
                db, company.id, page_url, text, source_type=source_type, fetched_at=fetched_at
            )
            if change_ev is not None:
                events.append(change_ev)
            save_snapshot(
                db,
                company.id,
                page_url,
                text,
                fetched_at=fetched_at,
                source_type=source_type,
            )
    return events


def _source_event_id(change_ev: ChangeEvent, candidate: CoreEventCandidate, index: int) -> str:
    """Deterministic source_event_id for deduplication (plan M6)."""
    payload = (
        f"{change_ev.company_id}:{change_ev.page_url}:{change_ev.timestamp.isoformat()}:"
        f"{candidate.event_type}:{index}:{(candidate.summary or '')[:200]}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def run_monitor_full(
    db: Session,
    *,
    workspace_id: str | UUID | None = None,
    company_ids: list[int] | None = None,
    llm_provider: object | None = None,
) -> dict:
    """Run monitor end-to-end: fetch → snapshots → diff → interpret → persist (M6).

    Runs run_monitor to collect ChangeEvents, interprets each via LLM, validates
    against core taxonomy, and persists each candidate as a SignalEvent with
    source='page_monitor' and deterministic source_event_id. Pack is resolved
    from workspace (default workspace when workspace_id omitted).

    Parameters
    ----------
    db : Session
        Active database session (caller manages transaction).
    workspace_id : str | UUID | None
        Workspace for pack resolution; uses DEFAULT_WORKSPACE_ID when omitted.
    company_ids : list[int] | None
        If provided, only these companies; else all with website_url.
    llm_provider : object | None
        Optional LLM provider for interpretation; None uses default.

    Returns
    -------
    dict
        status, change_events_count, events_stored, events_skipped_duplicate,
        companies_processed; error key on failure.
    """
    ws_id = str(workspace_id or DEFAULT_WORKSPACE_ID)
    pack_id: UUID | None = get_pack_for_workspace(db, ws_id)

    change_events = await run_monitor(db, company_ids=company_ids)
    if company_ids is not None:
        companies_processed = (
            db.query(Company)
            .filter(
                Company.id.in_(company_ids),
                Company.website_url.isnot(None),
            )
            .count()
        )
    else:
        companies_processed = db.query(Company).filter(Company.website_url.isnot(None)).count()

    events_stored = 0
    events_skipped_duplicate = 0

    for change_ev in change_events:
        candidates = interpret_change_event(
            change_ev,
            llm_provider=llm_provider,
        )
        event_time = change_ev.timestamp
        for idx, candidate in enumerate(candidates):
            source_event_id = _source_event_id(change_ev, candidate, idx)
            used_time = candidate.event_time if candidate.event_time is not None else event_time
            result = store_signal_event(
                db,
                company_id=change_ev.company_id,
                source=PAGE_MONITOR_SOURCE,
                source_event_id=source_event_id,
                event_type=candidate.event_type,
                event_time=used_time,
                title=candidate.title,
                summary=candidate.summary,
                url=candidate.url or change_ev.page_url,
                confidence=candidate.confidence,
                pack_id=pack_id,
            )
            if result is not None:
                events_stored += 1
            else:
                events_skipped_duplicate += 1

    return {
        "status": "completed",
        "change_events_count": len(change_events),
        "events_stored": events_stored,
        "events_skipped_duplicate": events_skipped_duplicate,
        "companies_processed": companies_processed,
    }
