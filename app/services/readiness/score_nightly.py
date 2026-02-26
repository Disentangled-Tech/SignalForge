"""Nightly TRS scoring job (Issue #104).

Scores all companies with SignalEvents in last 365 days OR on watchlist.
Writes readiness snapshots with explain payload and delta_1d.
Incrementally updates lead_feed projection after each company (Phase 3, Issue #225).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import JobRun, SignalEvent, Watchlist
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.services.esl.engagement_snapshot_writer import write_engagement_snapshot
from app.services.lead_feed.projection_builder import upsert_lead_feed_from_snapshots
from app.services.pack_resolver import get_core_pack_id, get_default_pack_id, get_pack_for_workspace
from app.services.readiness.snapshot_writer import write_readiness_snapshot

logger = logging.getLogger(__name__)


def run_score_nightly(
    db: Session,
    workspace_id: str | UUID | None = None,
    pack_id: str | UUID | None = None,
) -> dict:
    """Run nightly TRS scoring for all eligible companies (v2-spec §12, Issue #104).

    Companies to score:
    - Companies with any SignalEvent in last 365 days
    - OR companies on watchlist (is_active=True)

    One company failure does not stop the run (PRD error handling).
    Creates JobRun record for audit.

    Returns:
        dict with status, job_run_id, companies_scored, companies_skipped, error
    """
    if pack_id is not None:
        resolved_pack_id = pack_id
    elif workspace_id is not None:
        resolved_pack_id = get_pack_for_workspace(db, workspace_id)
    else:
        resolved_pack_id = get_default_pack_id(db)
    if isinstance(resolved_pack_id, str):
        resolved_pack_id = UUID(resolved_pack_id) if resolved_pack_id else None

    job = JobRun(job_type="score", status="running")
    if workspace_id is not None:
        job.workspace_id = (
            UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
        )
    if resolved_pack_id is not None:
        job.pack_id = resolved_pack_id
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        as_of = date.today()
        logger.info("Starting nightly score job, as_of=%s", as_of)
        cutoff_dt = datetime.combine(as_of - timedelta(days=365), datetime.min.time()).replace(
            tzinfo=UTC
        )

        # Company IDs with SignalEvents in last 365 days (pack-scoped when pack resolved)
        event_filters = [
            SignalEvent.company_id.isnot(None),
            SignalEvent.event_time >= cutoff_dt,
        ]
        if resolved_pack_id is not None:
            event_filters.append(
                or_(
                    SignalEvent.pack_id == resolved_pack_id,
                    SignalEvent.pack_id.is_(None),
                )
            )
        ids_from_events = {
            row[0]
            for row in db.query(SignalEvent.company_id).filter(*event_filters).distinct().all()
            if row[0] is not None
        }

        # Company IDs on watchlist (v2-spec §12: OR on watchlist)
        ids_from_watchlist = {
            row[0]
            for row in db.query(Watchlist.company_id).filter(Watchlist.is_active).distinct().all()
        }

        company_ids = ids_from_events | ids_from_watchlist

        companies_scored = 0
        companies_skipped = 0
        errors: list[str] = []

        companies_engagement = 0
        companies_esl_suppressed = 0
        ws_id = str(workspace_id or DEFAULT_WORKSPACE_ID)
        core_pack_id = get_core_pack_id(db)
        for company_id in company_ids:
            try:
                snapshot = write_readiness_snapshot(
                    db,
                    company_id,
                    as_of,
                    pack_id=resolved_pack_id,
                    core_pack_id=core_pack_id,
                )
                if snapshot is not None:
                    companies_scored += 1
                    # Write EngagementSnapshot after ReadinessSnapshot (Issue #106)
                    eng_snap = write_engagement_snapshot(
                        db,
                        company_id,
                        as_of,
                        pack_id=resolved_pack_id,
                        core_pack_id=core_pack_id,
                    )
                    if eng_snap is not None:
                        companies_engagement += 1
                        if eng_snap.esl_decision == "suppress":
                            companies_esl_suppressed += 1
                        # Incremental lead_feed update (Phase 3, Issue #225); M5: last_seen from core
                        upsert_lead_feed_from_snapshots(
                            db,
                            workspace_id=ws_id,
                            pack_id=resolved_pack_id,
                            as_of=as_of,
                            readiness_snapshot=snapshot,
                            engagement_snapshot=eng_snap,
                            core_pack_id=core_pack_id,
                        )
                else:
                    companies_skipped += 1
            except Exception as exc:
                msg = f"Company {company_id}: {exc}"
                logger.exception("Score failed for company %s", company_id)
                errors.append(msg)
                companies_skipped += 1

        job.finished_at = datetime.now(UTC)
        job.status = "completed"
        job.companies_processed = companies_scored
        job.companies_esl_suppressed = companies_esl_suppressed
        job.error_message = "; ".join(errors[:10]) if errors else None
        db.commit()

        logger.info(
            "Nightly score completed: scored=%d, skipped=%d, esl_suppressed=%d",
            companies_scored,
            companies_skipped,
            companies_esl_suppressed,
        )
        return {
            "status": "completed",
            "job_run_id": job.id,
            "companies_scored": companies_scored,
            "companies_engagement": companies_engagement,
            "companies_esl_suppressed": companies_esl_suppressed,
            "companies_skipped": companies_skipped,
            "error": "; ".join(errors) if errors else None,
        }

    except Exception as exc:
        logger.exception("Nightly score job failed")
        job.finished_at = datetime.now(UTC)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        return {
            "status": "failed",
            "job_run_id": job.id,
            "companies_scored": 0,
            "companies_engagement": 0,
            "companies_esl_suppressed": 0,
            "companies_skipped": 0,
            "error": str(exc),
        }
