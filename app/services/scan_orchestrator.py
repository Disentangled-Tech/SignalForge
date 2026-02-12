"""Scan orchestrator – coordinates per-company signal collection."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.job_run import JobRun
from app.services.page_discovery import discover_pages
from app.services.signal_storage import store_signal

logger = logging.getLogger(__name__)

# ── Source-type inference ────────────────────────────────────────────

_SOURCE_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("blog", ["blog", "articles", "posts"]),
    ("jobs", ["jobs", "job-openings", "open-positions"]),
    ("careers", ["careers", "career", "join-us", "work-with-us"]),
    ("news", ["news", "press", "announcements"]),
    ("about", ["about", "about-us", "team", "our-story"]),
]


def infer_source_type(url: str) -> str:
    """Infer the source type from a URL path.

    Returns one of: homepage, blog, jobs, careers, news, about.
    Falls back to "homepage" when no keyword matches.
    """
    path = urlparse(url).path.lower().strip("/")
    if not path:
        return "homepage"
    segments = path.split("/")
    for source_type, keywords in _SOURCE_TYPE_KEYWORDS:
        for keyword in keywords:
            if keyword in segments:
                return source_type
    return "homepage"


# ── Per-company scan ─────────────────────────────────────────────────


async def run_scan_company(db: Session, company_id: int) -> int:
    """Scan a single company and store discovered signals.

    Parameters
    ----------
    db : Session
        Active database session.
    company_id : int
        Company to scan.

    Returns
    -------
    int
        Number of *new* (non-duplicate) signals stored.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise ValueError(f"Company {company_id} not found")
    if not company.website_url:
        logger.info("Company %s has no website_url – skipping", company_id)
        return 0

    pages = await discover_pages(company.website_url)
    new_count = 0
    for page_url, page_text in pages:
        source_type = infer_source_type(page_url)
        result = store_signal(
            db,
            company_id=company_id,
            source_url=page_url,
            source_type=source_type,
            content_text=page_text,
        )
        if result is not None:
            new_count += 1
    return new_count


# ── Full scan ────────────────────────────────────────────────────────


async def run_scan_all(db: Session) -> JobRun:
    """Run a scan across **all** companies.

    Creates a ``JobRun`` record to track progress. Individual company
    failures are caught and logged so the remaining companies are still
    processed.

    Returns
    -------
    JobRun
        The completed (or failed) job-run record.
    """
    job = JobRun(job_type="scan", status="running")
    db.add(job)
    db.commit()
    db.refresh(job)

    companies = db.query(Company).all()
    processed = 0
    errors: list[str] = []

    for company in companies:
        if not company.website_url:
            continue
        try:
            await run_scan_company(db, company.id)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            msg = f"Company {company.id} ({company.name}): {exc}"
            logger.error("Scan failed – %s", msg)
            errors.append(msg)

    # Finalise JobRun
    job.finished_at = datetime.now(timezone.utc)
    job.companies_processed = processed

    if errors:
        job.error_message = "; ".join(errors)

    # "failed" only when ALL companies with URLs failed
    companies_with_url = [c for c in companies if c.website_url]
    if companies_with_url and processed == 0:
        job.status = "failed"
    else:
        job.status = "completed"

    db.commit()
    db.refresh(job)
    return job

