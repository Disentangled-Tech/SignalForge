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

from app.ingestion.adapters.crunchbase_adapter import CrunchbaseAdapter
from app.ingestion.adapters.delaware_socrata_adapter import DelawareSocrataAdapter
from app.ingestion.adapters.github_adapter import GitHubAdapter
from app.ingestion.adapters.newsapi_adapter import NewsAPIAdapter
from app.ingestion.adapters.producthunt_adapter import ProductHuntAdapter
from app.ingestion.adapters.test_adapter import TestAdapter
from app.ingestion.ingest import run_ingest
from app.models import JobRun
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.services.pack_resolver import get_default_pack_id

logger = logging.getLogger(__name__)


def _get_adapters() -> list:
    """Return list of adapters for daily ingestion.

    - INGEST_USE_TEST_ADAPTER=1: Returns [TestAdapter()] only (pytest).
    - Else: Build from env:
      - INGEST_CRUNCHBASE_ENABLED=1 and CRUNCHBASE_API_KEY set → CrunchbaseAdapter
      - INGEST_PRODUCTHUNT_ENABLED=1 and PRODUCTHUNT_API_TOKEN set → ProductHuntAdapter
      - INGEST_NEWSAPI_ENABLED=1 and NEWSAPI_API_KEY set → NewsAPIAdapter
      - INGEST_GITHUB_ENABLED=1 and GITHUB_TOKEN set → GitHubAdapter
      - INGEST_DELAWARE_SOCRATA_ENABLED=1 and INGEST_DELAWARE_SOCRATA_DATASET_ID set → DelawareSocrataAdapter
    Returns combined list (may be empty).
    """
    if os.getenv("INGEST_USE_TEST_ADAPTER", "").lower() in ("1", "true"):
        return [TestAdapter()]

    adapters: list = []
    if (
        os.getenv("INGEST_CRUNCHBASE_ENABLED", "").lower() in ("1", "true")
        and os.getenv("CRUNCHBASE_API_KEY", "").strip()
    ):
        adapters.append(CrunchbaseAdapter())
    if (
        os.getenv("INGEST_PRODUCTHUNT_ENABLED", "").lower() in ("1", "true")
        and os.getenv("PRODUCTHUNT_API_TOKEN", "").strip()
    ):
        adapters.append(ProductHuntAdapter())
    if (
        os.getenv("INGEST_NEWSAPI_ENABLED", "").lower() in ("1", "true")
        and os.getenv("NEWSAPI_API_KEY", "").strip()
    ):
        adapters.append(NewsAPIAdapter())
    token = os.getenv("GITHUB_TOKEN", "").strip() or os.getenv("GITHUB_PAT", "").strip()
    if (
        os.getenv("INGEST_GITHUB_ENABLED", "").lower() in ("1", "true")
        and token
    ):
        adapters.append(GitHubAdapter())
    dataset_id = os.getenv("INGEST_DELAWARE_SOCRATA_DATASET_ID", "").strip()
    if (
        os.getenv("INGEST_DELAWARE_SOCRATA_ENABLED", "").lower() in ("1", "true")
        and dataset_id
    ):
        adapters.append(DelawareSocrataAdapter())

    # Dev fallback: when no adapters configured and DEBUG=true, use TestAdapter
    # so "Run ingest" populates companies without API keys (Issue #90).
    if not adapters and os.getenv("DEBUG", "false").lower() in ("1", "true"):
        logger.info(
            "No ingest adapters configured; using TestAdapter (DEBUG=true). "
            "Set INGEST_CRUNCHBASE_ENABLED=1 and CRUNCHBASE_API_KEY (or other adapters) for production."
        )
        adapters = [TestAdapter()]

    return adapters


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
    # Audit: set pack_id and workspace_id for consistency with scan jobs
    resolved_workspace = (
        UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
    ) if workspace_id is not None else UUID(DEFAULT_WORKSPACE_ID)
    resolved_job_pack_id = pack_id or get_default_pack_id(db)
    if isinstance(resolved_job_pack_id, str):
        resolved_job_pack_id = UUID(str(resolved_job_pack_id)) if resolved_job_pack_id else None

    job = JobRun(
        job_type="ingest",
        status="running",
        workspace_id=resolved_workspace,
        pack_id=resolved_job_pack_id,
    )
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
                result = run_ingest(db, adapter, since, pack_id=resolved_job_pack_id)
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
