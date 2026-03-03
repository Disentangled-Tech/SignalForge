"""Scout analytics aggregation — workspace-scoped yield metrics from scout_runs (M5, Issue #282)."""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from app.schemas.scout import (
    ScoutAnalyticsFamilyBreakdown,
    ScoutAnalyticsResponse,
)


def get_scout_analytics(
    db: Session,
    workspace_id: UUID,
    since: date | None = None,
) -> ScoutAnalyticsResponse:
    """Return aggregate yield metrics for scout runs in the given workspace.

    Reads only from scout_runs and scout_evidence_bundles; filters by workspace_id
    and optionally by started_at >= since (start of day UTC). No cross-tenant data.

    Returns:
        runs_count: number of scout runs in scope
        total_bundles: sum of evidence bundles across those runs
        by_family: optional breakdown by query_families from config_snapshot
    """
    from datetime import UTC

    since_dt: datetime | None = None
    if since is not None:
        since_dt = datetime.combine(since, time.min).replace(tzinfo=UTC)

    base_filter = ScoutRun.workspace_id == workspace_id
    if since_dt is not None:
        base_filter = base_filter & (ScoutRun.started_at >= since_dt)

    runs_count = db.query(func.count(ScoutRun.id)).filter(base_filter).scalar() or 0

    # Total bundles: count ScoutEvidenceBundle rows whose run is in scope
    bundle_count_q = (
        db.query(func.count(ScoutEvidenceBundle.id))
        .join(ScoutRun, ScoutEvidenceBundle.scout_run_id == ScoutRun.run_id)
        .filter(ScoutRun.workspace_id == workspace_id)
    )
    if since_dt is not None:
        bundle_count_q = bundle_count_q.filter(ScoutRun.started_at >= since_dt)
    total_bundles = bundle_count_q.scalar() or 0

    # Optional by_family: aggregate config_snapshot.query_families across runs
    runs = db.query(ScoutRun.config_snapshot).filter(base_filter).all()
    family_runs: dict[str, int] = {}
    for (config,) in runs:
        if not isinstance(config, dict):
            continue
        families = config.get("query_families")
        if not isinstance(families, list):
            continue
        seen_this_run: set[str] = set()
        for f in families:
            if isinstance(f, str) and f.strip():
                fid = f.strip()
                if fid not in seen_this_run:
                    seen_this_run.add(fid)
                    family_runs[fid] = family_runs.get(fid, 0) + 1

    by_family = [
        ScoutAnalyticsFamilyBreakdown(family_id=k, runs_count=v)
        for k, v in sorted(family_runs.items())
    ]

    return ScoutAnalyticsResponse(
        runs_count=runs_count,
        total_bundles=total_bundles,
        by_family=by_family,
    )
