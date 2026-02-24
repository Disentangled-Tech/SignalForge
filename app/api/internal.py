"""Internal job endpoints for cron/scripts.

These endpoints are secured with a static token (X-Internal-Token header),
NOT cookie-based auth.  They are meant for automated triggers only.
"""

from __future__ import annotations

import logging
import secrets
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query
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


def _parse_uuid_or_422(value: str | None, param_name: str) -> None:
    """Validate value is a valid UUID; raise HTTPException 422 if not."""
    if not value or not value.strip():
        return
    try:
        from uuid import UUID

        UUID(value.strip())
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {param_name}: must be a valid UUID",
        ) from None


@router.post("/run_score")
async def run_score(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    workspace_id: str | None = Query(None, description="Workspace ID; uses default if omitted"),
    pack_id: str | None = Query(
        None, description="Pack UUID; uses workspace active pack if omitted"
    ),
):
    """Trigger nightly TRS scoring (Issue #104).

    Scores all companies with SignalEvents in last 365 days or on watchlist.
    Returns job summary with companies_scored, companies_skipped.

    Idempotency: Pass X-Idempotency-Key to skip duplicate runs. Use
    workspace-scoped keys (e.g. ``{workspace_id}:{timestamp}``) to avoid
    collisions across workspaces.

    Pack resolution (Phase 3): When pack_id omitted, uses workspace's
    active_pack_id; falls back to default pack when workspace has none.
    """
    from uuid import UUID

    from app.pipeline.executor import run_stage

    _parse_uuid_or_422(workspace_id, "workspace_id")
    _parse_uuid_or_422(pack_id, "pack_id")

    try:
        pack_uuid = UUID(pack_id.strip()) if pack_id and pack_id.strip() else None
        ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None
        result = run_stage(
            db,
            job_type="score",
            workspace_id=ws_id,
            pack_id=pack_uuid,
            idempotency_key=x_idempotency_key,
        )
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "companies_scored": result["companies_scored"],
            "companies_engagement": result.get("companies_engagement", 0),
            "companies_esl_suppressed": result.get("companies_esl_suppressed", 0),
            "companies_skipped": result["companies_skipped"],
            "error": result.get("error"),
        }
    except HTTPException:
        raise
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


@router.post("/run_derive")
async def run_derive_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    workspace_id: str | None = Query(None, description="Workspace ID; uses default if omitted"),
    pack_id: str | None = Query(
        None, description="Pack UUID; uses workspace active pack if omitted"
    ),
):
    """Trigger derive stage: populate signal_instances from SignalEvents (Phase 2).

    Run after ingest. Applies pack passthrough and pattern derivers. Idempotent.
    Pass X-Idempotency-Key to skip duplicate runs.
    Pack resolution: when pack_id omitted, uses workspace active_pack_id.
    """
    from uuid import UUID

    from app.pipeline.executor import run_stage

    _parse_uuid_or_422(workspace_id, "workspace_id")
    _parse_uuid_or_422(pack_id, "pack_id")

    try:
        pack_uuid = UUID(pack_id.strip()) if pack_id and pack_id.strip() else None
        ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None
        result = run_stage(
            db,
            job_type="derive",
            workspace_id=ws_id,
            pack_id=pack_uuid,
            idempotency_key=x_idempotency_key,
        )
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "instances_upserted": result.get("instances_upserted", 0),
            "events_processed": result.get("events_processed", 0),
            "events_skipped": result.get("events_skipped", 0),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Internal derive job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_ingest")
async def run_ingest_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    workspace_id: str | None = Query(None, description="Workspace ID; uses default if omitted"),
    pack_id: str | None = Query(
        None, description="Pack UUID; uses workspace active pack if omitted"
    ),
):
    """Trigger daily ingestion (Issue #90).

    Fetches events since last run (or 24h ago), persists with deduplication.
    Returns job summary with inserted, skipped_duplicate, skipped_invalid.

    Idempotency: Pass X-Idempotency-Key to skip duplicate runs. Use
    workspace-scoped keys (e.g. ``{workspace_id}:{timestamp}``) to avoid
    collisions across workspaces.
    Pack resolution: when pack_id omitted, uses workspace active_pack_id.
    Ingested events are written to the resolved pack (Phase 3).
    """
    from uuid import UUID

    from app.pipeline.executor import run_stage

    _parse_uuid_or_422(workspace_id, "workspace_id")
    _parse_uuid_or_422(pack_id, "pack_id")

    try:
        pack_uuid = UUID(pack_id.strip()) if pack_id and pack_id.strip() else None
        ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None
        result = run_stage(
            db,
            job_type="ingest",
            workspace_id=ws_id,
            pack_id=pack_uuid,
            idempotency_key=x_idempotency_key,
        )
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "inserted": result["inserted"],
            "skipped_duplicate": result["skipped_duplicate"],
            "skipped_invalid": result["skipped_invalid"],
            "errors_count": result["errors_count"],
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Internal ingest job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_update_lead_feed")
async def run_update_lead_feed_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    workspace_id: str | None = Query(None, description="Workspace ID; uses default if omitted"),
    pack_id: str | None = Query(
        None, description="Pack UUID; uses workspace active pack if omitted"
    ),
    as_of: date | None = Query(
        None,
        description="Snapshot date (YYYY-MM-DD). Default: today.",
    ),
):
    """Trigger lead_feed projection update (Phase 1, Issue #225, ADR-004).

    Builds projection from ReadinessSnapshot + EngagementSnapshot for as_of.
    Run after score. Idempotent. Pack resolution: when pack_id omitted,
    uses workspace active_pack_id.
    """
    from uuid import UUID

    from app.pipeline.executor import run_stage

    _parse_uuid_or_422(workspace_id, "workspace_id")
    _parse_uuid_or_422(pack_id, "pack_id")

    try:
        pack_uuid = UUID(pack_id.strip()) if pack_id and pack_id.strip() else None
        ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None
        result = run_stage(
            db,
            job_type="update_lead_feed",
            workspace_id=ws_id,
            pack_id=pack_uuid,
            idempotency_key=x_idempotency_key,
            as_of=as_of,
        )
        return {
            "status": result["status"],
            "job_run_id": result.get("job_run_id"),
):
    """Trigger update_lead_feed stage: populate lead_feed from snapshots (Phase 3).

    Run after score. Upserts lead_feed from ReadinessSnapshot + EngagementSnapshot.
    Idempotent. Pass X-Idempotency-Key to skip duplicate runs.
    """
    from app.pipeline.executor import run_stage

    try:
        result = run_stage(
            db,
            job_type="update_lead_feed",
            idempotency_key=x_idempotency_key,
        )
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "rows_upserted": result.get("rows_upserted", 0),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Internal update_lead_feed job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_backfill_lead_feed")
async def run_backfill_lead_feed_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    as_of: date | None = Query(
        None,
        description="Snapshot date (YYYY-MM-DD). Default: today.",
    ),
):
    """Backfill lead_feed for all workspaces (Phase 3, Issue #225).

    Runs build_lead_feed_from_snapshots for each workspace with a resolved pack.
    Idempotent: safe to re-run.
    """
    from app.services.lead_feed.run_update import run_backfill_lead_feed

    try:
        result = run_backfill_lead_feed(db, as_of=as_of)
        return {
            "status": result["status"],
            "workspaces_processed": result["workspaces_processed"],
            "total_rows_upserted": result["total_rows_upserted"],
            "errors": result.get("errors"),
        }
    except Exception as exc:
        logger.exception("Internal backfill_lead_feed job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_bias_audit")
async def run_bias_audit_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    month: date | None = Query(
        None,
        description="Report month (YYYY-MM-DD, first day). Default: previous month.",
    ),
):
    """Trigger monthly bias audit (Issue #112).

    Analyzes surfaced companies for funding, alignment, stage skew.
    Persists report; flags when any segment > 70%.
    """
    from app.services.bias_audit import run_bias_audit

    try:
        report_month = month
        if report_month is not None:
            report_month = report_month.replace(day=1)
        result = run_bias_audit(db, report_month)
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "report_id": result.get("report_id"),
            "surfaced_count": result.get("surfaced_count", 0),
            "flags": result.get("flags", []),
            "error": result.get("error"),
        }
    except Exception as exc:
        logger.exception("Internal bias audit failed")
        return {"status": "failed", "error": str(exc)}
