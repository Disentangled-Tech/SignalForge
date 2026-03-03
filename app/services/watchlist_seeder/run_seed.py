"""Orchestration: seed from bundles → derive → score (Issue #279 M3)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.services.pack_resolver import get_default_pack_id, get_pack_for_workspace
from app.services.watchlist_seeder.seeder import seed_from_bundles

logger = logging.getLogger(__name__)


def run_watchlist_seed(
    db: Session,
    bundle_ids: list[UUID],
    workspace_id: UUID | str | None = None,
    pack_id: UUID | None = None,
) -> dict[str, Any]:
    """Run watchlist seed flow: seed_from_bundles → run_deriver → run_score_nightly.

    Resolves workspace_id and pack_id like daily_aggregation: pack_id or
    get_pack_for_workspace(workspace_id) or get_default_pack_id(db). Returns
    combined status, seed_result, derive_result, and score_result. On no-pack
    resolution returns failed with empty derive/score results.
    """
    seed_result = seed_from_bundles(db, bundle_ids, workspace_id=workspace_id)
    ws_id = str(workspace_id or DEFAULT_WORKSPACE_ID)
    resolved_pack = pack_id or get_pack_for_workspace(db, ws_id) or get_default_pack_id(db)

    if resolved_pack is None:
        return {
            "status": "failed",
            "seed_result": seed_result.model_dump(),
            "derive_result": {},
            "score_result": {},
            "error": "No pack resolved for workspace",
        }

    derive_result: dict[str, Any] = {}
    score_result: dict[str, Any] = {}
    error_msg: str | None = None

    try:
        from app.pipeline.deriver_engine import run_deriver

        derive_result = run_deriver(db, workspace_id=ws_id, pack_id=resolved_pack)
    except Exception as exc:
        logger.exception("Watchlist seed flow: derive stage failed")
        error_msg = str(exc)
        derive_result = {"status": "failed", "error": error_msg}

    try:
        from app.services.readiness.score_nightly import run_score_nightly

        score_result = run_score_nightly(db, workspace_id=ws_id, pack_id=resolved_pack)
        if error_msg is None and score_result.get("status") != "completed":
            error_msg = score_result.get("error") or "Score stage did not complete"
    except Exception as exc:
        logger.exception("Watchlist seed flow: score stage failed")
        if error_msg is None:
            error_msg = str(exc)
        score_result = {"status": "failed", "error": str(exc)}

    completed = (
        derive_result.get("status") == "completed" and score_result.get("status") == "completed"
    )
    status = "completed" if completed and error_msg is None else "failed"
    return {
        "status": status,
        "seed_result": seed_result.model_dump(),
        "derive_result": derive_result,
        "score_result": score_result,
        "error": error_msg,
    }
