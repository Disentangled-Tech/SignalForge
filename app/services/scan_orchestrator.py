"""Scan orchestrator – coordinates per-company signal collection."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from uuid import UUID

if TYPE_CHECKING:
    from app.packs.loader import Pack

from sqlalchemy.orm import Session

from app.models.analysis_record import AnalysisRecord
from app.models.company import Company
from app.models.job_run import JobRun
from app.models.signal_pack import SignalPack
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.services.analysis import analyze_company
from app.services.pack_resolver import get_default_pack, get_default_pack_id, resolve_pack
from app.services.page_discovery import discover_pages
from app.services.scoring import (
    _get_signal_value,
    _is_signal_true,
    _normalize_signals,
    get_known_pain_signal_keys,
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

    logger.info(
        "Scanning company %s (%s) – website_url=%s", company_id, company.name, company.website_url
    )
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


def _extract_signal_values(
    pain_signals_json: dict[str, Any] | None,
    known_keys: set[str],
) -> dict[str, bool]:
    """Extract canonical signal name -> bool for comparison. Uses scoring normalization.

    Phase 2: known_keys from pack pain_signal_weights (get_known_pain_signal_keys).
    """
    if not pain_signals_json:
        return {}
    signals = pain_signals_json.get("signals", pain_signals_json)
    if not isinstance(signals, dict):
        return {}
    normalized = _normalize_signals(signals, known_keys)
    return {
        k: _is_signal_true(_get_signal_value(v)) for k, v in normalized.items() if k in known_keys
    }


def _analysis_changed(
    prev: AnalysisRecord | None,
    new: AnalysisRecord,
    db: Session,
    pack: Pack | None = None,
) -> bool:
    """Return True if analysis output (stage or pain signals) changed from previous.

    Companies with no prior analysis are not counted as changed.
    Phase 2: Uses pack pain_signal_weights for known keys.
    Phase 3: When pack provided, uses it for pack-aware change detection.
    """
    if prev is None:
        return False
    if (prev.stage or "").strip().lower() != (new.stage or "").strip().lower():
        return True
    known_keys = get_known_pain_signal_keys(db, pack=pack)
    prev_vals = _extract_signal_values(prev.pain_signals_json, known_keys)
    new_vals = _extract_signal_values(new.pain_signals_json, known_keys)
    all_keys = set(prev_vals) | set(new_vals)
    for k in all_keys:
        if prev_vals.get(k, False) != new_vals.get(k, False):
            return True
    return False


# ── Per-company full pipeline (scan + analysis + scoring) ─────────────


async def run_scan_company_full(
    db: Session,
    company_id: int,
    pack: Pack | None = None,
    pack_id: UUID | None = None,
) -> tuple[int, AnalysisRecord | None, bool]:
    """Run scan + analysis + scoring for a single company (no JobRun).

    Used by run_scan_all for bulk scans. Updates company.cto_need_score
    when analysis succeeds. Phase 2: Resolves pack and passes to analysis/scoring.
    When pack is provided (e.g. from run_scan_all), avoids per-company resolution.
    When pack_id is provided with pack, uses it for AnalysisRecord attribution
    (Phase 3: workspace-specific scans must attribute to workspace's pack, not default).
    """
    prev_analysis = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.company_id == company_id)
        .order_by(AnalysisRecord.created_at.desc())
        .first()
    )
    effective_pack = pack if pack is not None else get_default_pack(db)
    # Phase 3: Use provided pack_id for AnalysisRecord attribution. When pack_id is None
    # but pack is provided (e.g. workspace pack), derive pack_id from pack manifest to avoid
    # wrongly attributing to default pack. Fall back to default only when pack is None.
    if pack_id is not None:
        effective_pack_id = pack_id
    elif effective_pack is not None:
        pack_id_str = effective_pack.manifest.get("id") if isinstance(
            getattr(effective_pack, "manifest", None), dict
        ) else None
        version = effective_pack.manifest.get("version") if isinstance(
            getattr(effective_pack, "manifest", None), dict
        ) else None
        if pack_id_str and version:
            row = (
                db.query(SignalPack.id)
                .filter(
                    SignalPack.pack_id == pack_id_str,
                    SignalPack.version == version,
                )
                .first()
            )
            effective_pack_id = row[0] if row else get_default_pack_id(db)
        else:
            effective_pack_id = get_default_pack_id(db)
    else:
        effective_pack_id = None
    new_count = await run_scan_company(db, company_id)
    analysis = analyze_company(db, company_id, pack=effective_pack, pack_id=effective_pack_id)
    if analysis is not None:
        score_company(db, company_id, analysis, pack=effective_pack)
    changed = (
        _analysis_changed(prev_analysis, analysis, db, pack=effective_pack)
        if analysis
        else False
    )
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
        pack_id = get_default_pack_id(db)
        job = JobRun(
            job_type="company_scan",
            company_id=company_id,
            status="running",
            pack_id=pack_id,
            workspace_id=UUID(DEFAULT_WORKSPACE_ID),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    try:
        await run_scan_company(db, company_id)
    except Exception as exc:
        logger.error("Scan failed for company %s: %s", company_id, exc)
        job.finished_at = datetime.now(UTC)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        db.refresh(job)
        return job

    pack_id = job.pack_id if job.pack_id is not None else get_default_pack_id(db)
    pack = (
        resolve_pack(db, pack_id) if pack_id is not None else None
    ) or get_default_pack(db)
    try:
        analysis = analyze_company(db, company_id, pack=pack, pack_id=pack_id)
        if analysis is not None:
            score_company(db, company_id, analysis, pack=pack)
    except Exception as exc:
        logger.error("Analysis/scoring failed for company %s: %s", company_id, exc)
        job.finished_at = datetime.now(UTC)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        db.refresh(job)
        return job

    job.finished_at = datetime.now(UTC)
    job.status = "completed"
    job.error_message = None
    db.commit()
    db.refresh(job)
    return job


# ── Full scan ────────────────────────────────────────────────────────


async def run_scan_all(
    db: Session, workspace_id: str | UUID | None = None
) -> JobRun:
    """Run a scan across **all** companies.

    Creates a ``JobRun`` record to track progress. Individual company
    failures are caught and logged so the remaining companies are still
    processed.

    When workspace_id is provided (Phase 3), uses that workspace's active
    pack for analysis/scoring. Otherwise uses default pack and workspace.

    Returns
    -------
    JobRun
        The completed (or failed) job-run record.
    """
    from app.services.pack_resolver import get_pack_for_workspace

    ws_id = workspace_id or DEFAULT_WORKSPACE_ID
    ws_uuid = UUID(str(ws_id)) if isinstance(ws_id, str) else ws_id
    pack_id = (
        get_pack_for_workspace(db, ws_id)
        if workspace_id is not None
        else get_default_pack_id(db)
    ) or get_default_pack_id(db)

    job = JobRun(
        job_type="scan",
        status="running",
        pack_id=pack_id,
        workspace_id=ws_uuid,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    pack = (
        resolve_pack(db, pack_id)
        if pack_id is not None
        else get_default_pack(db)
    )
    companies = db.query(Company).all()
    companies_with_url = [c for c in companies if c.website_url]
    processed = 0
    changed_count = 0
    errors: list[str] = []

    if companies_with_url:
        for company in companies_with_url:
            try:
                _, _, changed = await run_scan_company_full(
                    db, company.id, pack=pack, pack_id=pack_id
                )
                processed += 1
                if changed:
                    changed_count += 1
            except Exception as exc:  # noqa: BLE001
                msg = f"Company {company.id} ({company.name}): {exc}"
                logger.error("Scan failed – %s", msg)
                errors.append(msg)
    else:
        # No companies with website URLs – nothing to scan (Issue #162)
        job.error_message = (
            "No companies with website URLs. Add companies with website URLs and run Scan All."
        )

    # Finalise JobRun
    job.finished_at = datetime.now(UTC)
    job.companies_processed = processed
    job.companies_analysis_changed = changed_count

    if errors:
        job.error_message = "; ".join(errors)

    # "failed" only when companies_with_url non-empty but ALL failed
    if companies_with_url and processed == 0:
        job.status = "failed"
    else:
        job.status = "completed"

    db.commit()
    db.refresh(job)
    return job
