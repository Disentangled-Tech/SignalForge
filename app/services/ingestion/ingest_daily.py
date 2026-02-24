"""Daily ingestion job orchestrator (Issue #90).

Schedules ingestion via existing pipeline: fetch since last run,
normalize, resolve companies, store with deduplication.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.ingestion.adapters.test_adapter import TestAdapter
from app.ingestion.ingest import run_ingest
from app.models import JobRun

logger = logging.getLogger(__name__)


def _get_adapters() -> list:
    """Return list of adapters for daily ingestion.

    TestAdapter only when INGEST_USE_TEST_ADAPTER=1 (pytest sets this).
    Production returns [] until real adapters (Crunchbase, etc.) are configured.
    """
    if os.getenv("INGEST_USE_TEST_ADAPTER", "").lower() in ("1", "true"):
        return [TestAdapter()]
    return []


def run_ingest_daily(
    db: Session,
    workspace_id: str | UUID | None = None,
    pack_id: str | UUID | None = None,
) -> dict:
    """Run daily ingestion across all adapters (v2-spec §12, Issue #90).

    Creates JobRun record. Computes since from last completed ingest
    or falls back to now - 24h. One adapter failure does not stop the run.

    Returns:
        dict with status, job_run_id, inserted, skipped_duplicate,
        skipped_invalid, errors_count, error
    """
    job = JobRun(job_type="ingest", status="running")
    if workspace_id is not None:
        job.workspace_id = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
    if pack_id is not None:
        job.pack_id = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        # Compute since: last ingest finished_at or now - 24h
        last_job = (
            db.query(JobRun)
            .filter(
                JobRun.job_type == "ingest",
                JobRun.status == "completed",
                JobRun.finished_at.isnot(None),
            )
            .order_by(JobRun.finished_at.desc())
            .first()
        )
        if last_job and last_job.finished_at:
            since = last_job.finished_at
        else:
            since = datetime.now(UTC) - timedelta(hours=24)

        adapters = _get_adapters()
        total_inserted = 0
        total_skipped_duplicate = 0
        total_skipped_invalid = 0
        all_errors: list[str] = []

        for adapter in adapters:
            try:
                result = run_ingest(db, adapter, since)
                total_inserted += result["inserted"]
                total_skipped_duplicate += result["skipped_duplicate"]
                total_skipped_invalid += result["skipped_invalid"]
                all_errors.extend(result["errors"])
            except Exception as exc:
                msg = f"{adapter.source_name}: {exc}"
                logger.exception("Ingest failed for adapter %s", adapter.source_name)
                all_errors.append(msg)

        job.finished_at = datetime.now(UTC)
        job.status = "completed"
        job.companies_processed = total_inserted
        job.error_message = "; ".join(all_errors[:10]) if all_errors else None
        db.commit()

        return {
            "status": "completed",
            "job_run_id": job.id,
            "inserted": total_inserted,
            "skipped_duplicate": total_skipped_duplicate,
            "skipped_invalid": total_skipped_invalid,
            "errors_count": len(all_errors),
            "error": "; ".join(all_errors) if all_errors else None,
        }

    except Exception as exc:
        logger.exception("Daily ingest job failed")
        job.finished_at = datetime.now(UTC)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        return {
            "status": "failed",
            "job_run_id": job.id,
            "inserted": 0,
            "skipped_duplicate": 0,
            "skipped_invalid": 0,
            "errors_count": 0,
            "error": str(exc),
        }
