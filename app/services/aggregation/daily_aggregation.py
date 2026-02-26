"""Daily signal aggregation job (Issue #246, Phase 4).

Orchestrates ingest → derive → score. On success, queries ranked companies
via get_emerging_companies. One adapter failure does not kill ingest.
Stage failure: derive/score run on existing data; partial result returned on error.
Unified orchestrator for cron. Runs stages in order, returns ranked companies.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.job_run import JobRun
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.services.briefing import get_emerging_companies
from app.services.pack_resolver import get_default_pack_id, get_pack_for_workspace

logger = logging.getLogger(__name__)


def run_daily_aggregation(
    db: Session,
    workspace_id: str | UUID | None = None,
    pack_id: str | UUID | None = None,
) -> dict[str, Any]:
    """Run unified daily aggregation: ingest → derive → score.

    Resolves pack via pack_id or get_pack_for_workspace(workspace_id) or
    get_default_pack_id(db). Passes workspace_id and pack_id to each stage.

    On success, calls get_emerging_companies for ranked list. Logs ranked
    companies (name, composite, band) to console.

    Returns:
        dict with status, job_run_id, ingest_result, derive_result,
        score_result, ranked_companies, ranked_count, error
    """
    ws_id = str(workspace_id or DEFAULT_WORKSPACE_ID)
    resolved_pack = pack_id or get_pack_for_workspace(db, ws_id) or get_default_pack_id(db)

    job = JobRun(
        job_type="daily_aggregation",
        status="running",
        workspace_id=UUID(ws_id) if ws_id else None,
        pack_id=resolved_pack,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    ingest_result: dict[str, Any] = {}
    derive_result: dict[str, Any] = {}
    score_result: dict[str, Any] = {}
    ranked_companies: list[dict[str, Any]] = []
    error_msg: str | None = None

    try:
        # Stage 1: Ingest
        from app.services.ingestion.ingest_daily import run_ingest_daily

        ingest_result = run_ingest_daily(db, workspace_id=ws_id, pack_id=resolved_pack)

        # Stage 2: Derive (run even if ingest had adapter errors; one failure non-fatal)
        from app.pipeline.deriver_engine import run_deriver

        derive_result = run_deriver(db, workspace_id=ws_id, pack_id=resolved_pack)

        # Stage 3: Score
        from app.services.readiness.score_nightly import run_score_nightly

        score_result = run_score_nightly(db, workspace_id=ws_id, pack_id=resolved_pack)

        # Ranked list for monitoring/logging: threshold=0 to include all scored companies
        # (orchestrator output; briefing view applies its own filtering)
        as_of = date.today()
        emerging = get_emerging_companies(
            db,
            as_of,
            limit=20,
            outreach_score_threshold=0,
            pack_id=resolved_pack,
            workspace_id=ws_id,
        )
        for rs, es, company in emerging:
            band = es.esl_decision or es.engagement_type or "N/A"
            ranked_companies.append(
                {
                    "company_name": company.name,
                    "composite": rs.composite,
                    "band": band,
                }
            )
            logger.info(
                "Ranked: %s composite=%d band=%s",
                company.name,
                rs.composite,
                band,
            )

        job.status = "completed"
        job.companies_processed = score_result.get("companies_scored", 0)

    except Exception as exc:
        logger.exception("Daily aggregation failed")
        error_msg = str(exc)
        job.status = "failed"
        job.error_message = error_msg

    job.finished_at = datetime.now(UTC)
    db.commit()

    return {
        "status": job.status,
        "job_run_id": job.id,
        "ingest_result": ingest_result,
        "derive_result": derive_result,
        "score_result": score_result,
        "ranked_companies": ranked_companies,
        "ranked_count": len(ranked_companies),
        "error": error_msg,
    }
