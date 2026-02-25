"""Run update_lead_feed job (Phase 1, Issue #225).

Creates JobRun, calls build_lead_feed_from_snapshots, returns result.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.job_run import JobRun
from app.services.lead_feed import build_lead_feed_from_snapshots


def run_update_lead_feed(
    db: Session,
    workspace_id: str | UUID | None = None,
    pack_id: str | UUID | None = None,
    as_of: date | None = None,
) -> dict:
    """Run lead_feed projection update for workspace/pack.

    Creates JobRun record. Builds projection from ReadinessSnapshot +
    EngagementSnapshot for as_of (default: today). Idempotent: safe to re-run.

    Returns:
        dict with status, job_run_id, rows_upserted, error
    """
    from app.pipeline.stages import DEFAULT_WORKSPACE_ID
    from app.services.pack_resolver import get_pack_for_workspace

    ws_id = str(workspace_id or DEFAULT_WORKSPACE_ID)
    pack = pack_id or get_pack_for_workspace(db, ws_id)
    if pack is None:
        return {
            "status": "failed",
            "job_run_id": None,
            "rows_upserted": 0,
            "error": "No pack resolved for workspace",
        }

    pack_uuid = UUID(str(pack)) if isinstance(pack, str) else pack
    as_of_date = as_of or date.today()

    job = JobRun(job_type="update_lead_feed", status="running")
    job.workspace_id = UUID(ws_id) if ws_id else None
    job.pack_id = pack_uuid
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        count = build_lead_feed_from_snapshots(
            db, workspace_id=ws_id, pack_id=pack_uuid, as_of=as_of_date
        )
        job.finished_at = datetime.now(UTC)
        job.status = "completed"
        job.companies_processed = count
        job.error_message = None
        db.commit()
        return {
            "status": "completed",
            "job_run_id": job.id,
            "rows_upserted": count,
            "error": None,
        }
    except Exception as exc:
        job.finished_at = datetime.now(UTC)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        return {
            "status": "failed",
            "job_run_id": job.id,
            "rows_upserted": 0,
            "error": str(exc),
        }


def run_backfill_lead_feed(
    db: Session,
    as_of: date | None = None,
) -> dict:
    """Backfill lead_feed for all workspaces with a resolved pack (Phase 3).

    Iterates workspaces, runs build_lead_feed_from_snapshots for each.
    Idempotent: safe to re-run.

    TODO(performance): Consider rate limiting or batching when many workspaces
    exist to avoid long-running transactions and connection exhaustion.

    Rollback behavior: When one workspace fails, db.rollback() rolls back only
    the current transaction. Prior workspace commits (db.commit() after each
    successful workspace) are already persisted. This is intentional: per-
    workspace isolation allows partial success (e.g. 8 of 10 workspaces
    succeed). Use all-or-nothing behavior only if you wrap the loop in a
    single transaction and commit once at the end.

    Returns:
        dict with status, workspaces_processed, total_rows_upserted, errors
    """
    from app.models.workspace import Workspace
    from app.services.pack_resolver import get_pack_for_workspace

    as_of_date = as_of or date.today()
    workspaces = db.query(Workspace).all()
    total_rows = 0
    errors: list[str] = []

    for ws in workspaces:
        pack = get_pack_for_workspace(db, str(ws.id))
        if pack is None:
            continue
        try:
            count = build_lead_feed_from_snapshots(
                db,
                workspace_id=str(ws.id),
                pack_id=pack,
                as_of=as_of_date,
            )
            db.commit()
            total_rows += count
        except Exception as exc:
            errors.append(f"workspace {ws.id}: {exc}")
            db.rollback()

    return {
        "status": "completed" if not errors else "completed_with_errors",
        "workspaces_processed": len(workspaces),
        "total_rows_upserted": total_rows,
        "errors": errors[:10] if errors else None,
    }
