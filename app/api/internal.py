"""Internal job endpoints for cron/scripts.

These endpoints are secured with a static token (X-Internal-Token header),
NOT cookie-based auth.  They are meant for automated triggers only.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", include_in_schema=False)


# ── Token dependency ────────────────────────────────────────────────


def _require_internal_token(x_internal_token: str = Header(...)) -> None:
    """Validate the internal job token from the request header.

    Uses constant-time comparison to prevent timing attacks.
    Raises 403 if the token is empty or does not match the configured value.
    """
    expected = get_settings().internal_job_token
    if not expected or not secrets.compare_digest(x_internal_token, expected):
        logger.warning("Internal endpoint auth failed: invalid or missing token")
        raise HTTPException(status_code=403, detail="Invalid internal token")


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/run_scan")
async def run_scan(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
):
    """Trigger a full scan across all companies.

    Returns the completed JobRun summary.
    """
    from app.services.scan_orchestrator import run_scan_all

    try:
        job = await run_scan_all(db)
        return {
            "status": job.status,
            "job_run_id": job.id,
            "companies_processed": job.companies_processed,
        }
    except Exception as exc:
        logger.exception("Internal scan failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_briefing")
async def run_briefing(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
):
    """Trigger briefing generation for top companies.

    Returns the number of briefing items generated.
    """
    from app.services.briefing import generate_briefing

    try:
        items = generate_briefing(db)
        return {"status": "completed", "items_generated": len(items)}
    except Exception as exc:
        logger.exception("Internal briefing generation failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_score")
async def run_score(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
):
    """Trigger nightly TRS scoring (Issue #104).

    Scores all companies with SignalEvents in last 365 days or on watchlist.
    Returns job summary with companies_scored, companies_skipped.
    """
    from app.services.readiness.score_nightly import run_score_nightly

    try:
        result = run_score_nightly(db)
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "companies_scored": result["companies_scored"],
            "companies_engagement": result.get("companies_engagement", 0),
            "companies_skipped": result["companies_skipped"],
            "error": result.get("error"),
        }
    except Exception as exc:
        logger.exception("Internal score job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_alert_scan")
async def run_alert_scan(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
):
    """Trigger daily readiness delta alert scan (Issue #92).

    Run after score_nightly. Creates alerts when |delta| >= threshold.
    Returns alerts_created, companies_scanned.
    """
    from app.services.readiness.alert_scan import run_alert_scan

    try:
        result = run_alert_scan(db)
        return {
            "status": result["status"],
            "alerts_created": result["alerts_created"],
            "companies_scanned": result["companies_scanned"],
        }
    except Exception as exc:
        logger.exception("Internal alert scan failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_ingest")
async def run_ingest_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
):
    """Trigger daily ingestion (Issue #90).

    Fetches events since last run (or 24h ago), persists with deduplication.
    Returns job summary with inserted, skipped_duplicate, skipped_invalid.
    """
    from app.services.ingestion.ingest_daily import run_ingest_daily

    try:
        result = run_ingest_daily(db)
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "inserted": result["inserted"],
            "skipped_duplicate": result["skipped_duplicate"],
            "skipped_invalid": result["skipped_invalid"],
            "errors_count": result["errors_count"],
            "error": result.get("error"),
        }
    except Exception as exc:
        logger.exception("Internal ingest job failed")
        return {"status": "failed", "error": str(exc)}

