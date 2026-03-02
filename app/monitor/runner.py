"""Monitor runner: fetch → snapshot → diff → collect ChangeEvents (M4, Issue #280)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import urljoin

from sqlalchemy.orm import Session

from app.models.company import Company
from app.monitor.detector import detect_change
from app.monitor.schemas import ChangeEvent
from app.monitor.snapshot_store import save_snapshot
from app.services.extractor import extract_text
from app.services.fetcher import fetch_page

logger = logging.getLogger(__name__)

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
