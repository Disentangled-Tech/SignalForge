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

