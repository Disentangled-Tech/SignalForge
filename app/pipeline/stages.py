"""Pipeline stage protocol and registry (Phase 1, Issue #192)."""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.orm import Session

# Default workspace until multi-workspace (plan §2)
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


class StageResult(dict[str, Any]):
    """Result from a pipeline stage. Extends dict for backward compatibility."""


class PipelineStage(Protocol):
    """Protocol for pipeline stages.

    Stages receive db, workspace_id, pack_id and optional kwargs.
    Return a dict suitable for API response (status, job_run_id, etc.).
    """

    def __call__(
        self,
        db: Session,
        workspace_id: str,
        pack_id: str | None,
        **kwargs: Any,
    ) -> StageResult:
        """Execute the stage. Returns result dict."""
        ...


def _ingest_stage(
    db: Session,
    workspace_id: str,
    pack_id: str | None,
    **kwargs: Any,
) -> StageResult:
    """Ingest stage: wraps run_ingest_daily."""
    from app.services.ingestion.ingest_daily import run_ingest_daily

    return StageResult(run_ingest_daily(db, workspace_id=workspace_id, pack_id=pack_id))


def _score_stage(
    db: Session,
    workspace_id: str,
    pack_id: str | None,
    **kwargs: Any,
) -> StageResult:
    """Score stage: wraps run_score_nightly."""
    from app.services.readiness.score_nightly import run_score_nightly

    return StageResult(run_score_nightly(db, workspace_id=workspace_id, pack_id=pack_id))


def _derive_stage(
    db: Session,
    workspace_id: str,
    pack_id: str | None,
    **kwargs: Any,
) -> StageResult:
    """Derive stage: populates signal_instances from SignalEvents (Phase 2)."""
    from app.pipeline.deriver_engine import run_deriver

    return StageResult(
        run_deriver(db, workspace_id=workspace_id, pack_id=pack_id)
    )


def _update_lead_feed_stage(
    db: Session,
    workspace_id: str,
    pack_id: str | None,
    **kwargs: Any,
) -> StageResult:
    """Update lead_feed stage: builds projection from snapshots (Phase 1, Issue #225)."""
    from app.services.lead_feed.run_update import run_update_lead_feed

    return StageResult(
        run_update_lead_feed(
            db,
            workspace_id=workspace_id,
            pack_id=pack_id,
            as_of=kwargs.get("as_of"),
        )
    )


# Registry: job_type -> callable (db, workspace_id, pack_id, **kwargs) -> dict
STAGE_REGISTRY: dict[str, PipelineStage] = {
    "ingest": _ingest_stage,
    "derive": _derive_stage,
    "score": _score_stage,
    "update_lead_feed": _update_lead_feed_stage,
}
