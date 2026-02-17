"""Scan orchestrator – coordinates per-company signal collection."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.analysis_record import AnalysisRecord
from app.models.company import Company
from app.models.job_run import JobRun
from app.services.analysis import analyze_company
from app.services.page_discovery import discover_pages
from app.services.scoring import (
    DEFAULT_SIGNAL_WEIGHTS,
    _get_signal_value,
    _is_signal_true,
    _normalize_signals,
    score_company,
)
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

    logger.info("Scanning company %s (%s) – website_url=%s", company_id, company.name, company.website_url)
    pages = await discover_pages(company.website_url)
    logger.info("Company %s: discovered %d pages with content", company_id, len(pages))
    new_count = 0
    for page_url, page_text, raw_html in pages:
        source_type = infer_source_type(page_url)
        result = store_signal(
            db,
            company_id=company_id,
            source_url=page_url,
            source_type=source_type,
            content_text=page_text,
            raw_html=raw_html,
        )
        if result is not None:
            new_count += 1
    return new_count


# ── Change detection (issue #61) ──────────────────────────────────────


def _extract_signal_values(pain_signals_json: dict[str, Any] | None) -> dict[str, bool]:
    """Extract canonical signal name -> bool for comparison. Uses scoring normalization."""
    if not pain_signals_json:
        return {}
    signals = pain_signals_json.get("signals", pain_signals_json)
    if not isinstance(signals, dict):
        return {}
    normalized = _normalize_signals(signals)
    return {
        k: _is_signal_true(_get_signal_value(v))
        for k, v in normalized.items()
        if k in DEFAULT_SIGNAL_WEIGHTS
    }


def _analysis_changed(
    prev: AnalysisRecord | None, new: AnalysisRecord
) -> bool:
    """Return True if analysis output (stage or pain signals) changed from previous.

    Companies with no prior analysis are not counted as changed.
    """
    if prev is None:
        return False
    if (prev.stage or "").strip().lower() != (new.stage or "").strip().lower():
        return True
    prev_vals = _extract_signal_values(prev.pain_signals_json)
    new_vals = _extract_signal_values(new.pain_signals_json)
    all_keys = set(prev_vals) | set(new_vals)
    for k in all_keys:
        if prev_vals.get(k, False) != new_vals.get(k, False):
            return True
    return False


# ── Per-company full pipeline (scan + analysis + scoring) ─────────────


async def run_scan_company_full(
    db: Session, company_id: int
) -> tuple[int, AnalysisRecord | None, bool]:
    """Run scan + analysis + scoring for a single company (no JobRun).

    Used by run_scan_all for bulk scans. Updates company.cto_need_score
    when analysis succeeds.

    Returns
    -------
    tuple[int, AnalysisRecord | None, bool]
        (new_signals_count, analysis_record or None, analysis_changed)
    """
    prev_analysis = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.company_id == company_id)
        .order_by(AnalysisRecord.created_at.desc())
        .first()
    )
    new_count = await run_scan_company(db, company_id)
    analysis = analyze_company(db, company_id)
    if analysis is not None:
        score_company(db, company_id, analysis)
    changed = _analysis_changed(prev_analysis, analysis) if analysis else False
    return new_count, analysis, changed


# ── Per-company scan with job tracking ───────────────────────────────


async def run_scan_company_with_job(
    db: Session, company_id: int, *, job_id: int | None = None
) -> JobRun:
    """Run scan + analysis + scoring for a single company, tracked by JobRun.

    When job_id is provided, updates that existing JobRun. Otherwise creates
    a new JobRun with job_type="company_scan" and company_id. Runs
    run_scan_company, then analyze_company, then score_company. Updates
    JobRun status, finished_at, and error_message on completion or failure.

    Parameters
    ----------
    db : Session
        Active database session.
    company_id : int
        Company to scan.
    job_id : int | None
        Optional ID of an existing JobRun to update (e.g. created by the view).

    Returns
    -------
    JobRun
        The created or updated job-run record.
    """
    if job_id is not None:
        job = db.query(JobRun).filter(JobRun.id == job_id).first()
        if job is None:
            raise ValueError(f"JobRun {job_id} not found")
    else:
        job = JobRun(
            job_type="company_scan",
            company_id=company_id,
            status="running",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    try:
        await run_scan_company(db, company_id)
    except Exception as exc:
        logger.error("Scan failed for company %s: %s", company_id, exc)
        job.finished_at = datetime.now(timezone.utc)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        db.refresh(job)
        return job

    try:
        analysis = analyze_company(db, company_id)
        if analysis is not None:
            score_company(db, company_id, analysis)
    except Exception as exc:
        logger.error("Analysis/scoring failed for company %s: %s", company_id, exc)
        job.finished_at = datetime.now(timezone.utc)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        db.refresh(job)
        return job

    job.finished_at = datetime.now(timezone.utc)
    job.status = "completed"
    job.error_message = None
    db.commit()
    db.refresh(job)
    return job


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
    changed_count = 0
    errors: list[str] = []

    for company in companies:
        if not company.website_url:
            continue
        try:
            _, _, changed = await run_scan_company_full(db, company.id)
            processed += 1
            if changed:
                changed_count += 1
        except Exception as exc:  # noqa: BLE001
            msg = f"Company {company.id} ({company.name}): {exc}"
            logger.error("Scan failed – %s", msg)
            errors.append(msg)

    # Finalise JobRun
    job.finished_at = datetime.now(timezone.utc)
    job.companies_processed = processed
    job.companies_analysis_changed = changed_count

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

