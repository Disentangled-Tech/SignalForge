"""Daily aggregation job: ingest → derive → score (Issue #246).

Unified orchestrator for cron. Runs stages in order, returns ranked companies.
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.services.briefing import get_emerging_companies
from app.services.pack_resolver import get_default_pack_id, get_pack_for_workspace

logger = logging.getLogger(__name__)


def run_daily_aggregation(
    db: Session,
    workspace_id: str | UUID | None = None,
    pack_id: str | UUID | None = None,
) -> dict:
    """Run ingest → derive → score, return ranked companies (Issue #246).

    Pack resolution: pack_id or get_pack_for_workspace(db, workspace_id) or
    get_default_pack_id(db).

    Returns:
        dict with status, ingest_result, derive_result, score_result,
        ranked_companies (list of {name, composite, band}), ranked_count, error.
    """
    from app.pipeline.deriver_engine import run_deriver
    from app.services.ingestion.ingest_daily import run_ingest_daily
    from app.services.readiness.score_nightly import run_score_nightly

    ws_id = str(workspace_id or DEFAULT_WORKSPACE_ID)
    resolved_pack = pack_id or get_pack_for_workspace(db, ws_id) or get_default_pack_id(db)
    if resolved_pack is None:
        return {
            "status": "failed",
            "ingest_result": None,
            "derive_result": None,
            "score_result": None,
            "ranked_companies": [],
            "ranked_count": 0,
            "error": "No pack resolved for workspace",
        }

    pack_uuid = UUID(str(resolved_pack)) if isinstance(resolved_pack, str) else resolved_pack

    ingest_result = run_ingest_daily(db, workspace_id=ws_id, pack_id=pack_uuid)
    if ingest_result["status"] == "failed":
        return {
            "status": "failed",
            "ingest_result": ingest_result,
            "derive_result": None,
            "score_result": None,
            "ranked_companies": [],
            "ranked_count": 0,
            "error": ingest_result.get("error"),
        }

    derive_result = run_deriver(db, workspace_id=ws_id, pack_id=pack_uuid)
    if derive_result["status"] == "failed":
        return {
            "status": "failed",
            "ingest_result": ingest_result,
            "derive_result": derive_result,
            "score_result": None,
            "ranked_companies": [],
            "ranked_count": 0,
            "error": derive_result.get("error"),
        }

    score_result = run_score_nightly(db, workspace_id=ws_id, pack_id=pack_uuid)
    if score_result["status"] == "failed":
        return {
            "status": "failed",
            "ingest_result": ingest_result,
            "derive_result": derive_result,
            "score_result": score_result,
            "ranked_companies": [],
            "ranked_count": 0,
            "error": score_result.get("error"),
        }

    as_of = date.today()
    emerging = get_emerging_companies(
        db,
        as_of,
        workspace_id=ws_id,
        pack_id=pack_uuid,
        limit=10,
        outreach_score_threshold=0,
    )
    ranked: list[dict] = []
    for rs, es, company in emerging:
        band = getattr(es, "esl_decision", None) or getattr(es, "recommendation_band", None)
        ranked.append({
            "name": company.name if company else "",
            "composite": rs.composite if rs else 0,
            "band": str(band) if band else "",
        })
        logger.info(
            "Ranked: %s composite=%s band=%s",
            company.name if company else "?",
            rs.composite if rs else 0,
            band,
        )

    return {
        "status": "completed",
        "ingest_result": ingest_result,
        "derive_result": derive_result,
        "score_result": score_result,
        "ranked_companies": ranked,
        "ranked_count": len(ranked),
        "error": None,
    }
