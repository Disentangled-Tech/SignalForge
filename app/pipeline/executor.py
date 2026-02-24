"""Job executor: idempotency, rate limits, stage dispatch (Phase 1, Issue #192)."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.job_run import JobRun
from app.pipeline.rate_limits import check_workspace_rate_limit
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.services.pack_resolver import get_default_pack_id

logger = logging.getLogger(__name__)


def run_stage(
    db: Session,
    job_type: str,
    workspace_id: str | UUID | None = None,
    pack_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Run a pipeline stage with idempotency and rate limit checks.

    Resolves default workspace and pack when not provided.
    Returns cached result if idempotency_key matches a recent completed run
    for the same workspace and job_type.
    Raises HTTPException 429 if rate limit exceeded.

    Idempotency keys are workspace-scoped. Callers should use
    workspace-scoped keys (e.g. ``{workspace_id}:{timestamp}``) to avoid
    collisions when the same key may be used across workspaces.
    """
    ws_id = str(workspace_id or DEFAULT_WORKSPACE_ID)
    pack = pack_id or get_default_pack_id(db)
    pack_str = str(pack) if pack else None

    if idempotency_key:
        ws_uuid = UUID(ws_id) if ws_id else None
        existing = (
            db.query(JobRun)
            .filter(
                JobRun.idempotency_key == idempotency_key,
                JobRun.job_type == job_type,
                JobRun.workspace_id == ws_uuid,
            )
            .order_by(JobRun.started_at.desc())
            .first()
        )
        if existing and existing.status == "completed":
            logger.info(
                "Idempotent skip: job_type=%s idempotency_key=%s job_run_id=%s",
                job_type,
                idempotency_key,
                existing.id,
            )
            return _cached_result(existing, job_type)

    if not check_workspace_rate_limit(db, ws_id, job_type):
        raise HTTPException(
            status_code=429,
            detail="Workspace job rate limit exceeded",
        )

    from app.pipeline.stages import STAGE_REGISTRY

    stage = STAGE_REGISTRY.get(job_type)
    if not stage:
        raise ValueError(f"Unknown job_type: {job_type}")

    return stage(db, workspace_id=ws_id, pack_id=pack_str, **{})


def _cached_result(job: JobRun, job_type: str) -> dict:
    """Build response dict from a completed JobRun.

    Note: Cached responses are approximate. JobRun does not store
    companies_engagement or companies_skipped; score cache uses
    companies_processed for both. Ingest cache uses companies_processed
    for inserted; skipped_duplicate/skipped_invalid are 0.
    """
    base = {
        "status": job.status,
        "job_run_id": job.id,
    }
    if job_type == "ingest":
        return {
            **base,
            "inserted": job.companies_processed or 0,
            "skipped_duplicate": 0,
            "skipped_invalid": 0,
            "errors_count": 0,
            "error": job.error_message,
        }
    if job_type == "score":
        return {
            **base,
            "companies_scored": job.companies_processed or 0,
            "companies_engagement": job.companies_processed or 0,
            "companies_skipped": 0,
            "error": job.error_message,
        }
    if job_type == "derive":
        return {
            **base,
            "instances_upserted": job.companies_processed or 0,
            "events_processed": 0,
            "events_skipped": 0,
            "error": job.error_message,
        }
    if job_type == "update_lead_feed":
        return {
            **base,
            "rows_upserted": job.companies_processed or 0,
            "error": job.error_message,
        }
    return base
