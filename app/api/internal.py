"""Internal job endpoints for cron/scripts.

These endpoints are secured with a static token (X-Internal-Token header),
NOT cookie-based auth.  They are meant for automated triggers only.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import validate_uuid_param_or_422
from app.config import get_settings
from app.db.session import get_db
from app.schemas.evidence import StoreEvidenceRequest
from app.schemas.scout import (
    RunScoutRequest,
    ScoutAnalyticsResponse,
    ScoutRunListItem,
    ScoutRunListResponse,
)
from app.schemas.seeder import SeedFromBundlesRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", include_in_schema=False)


# ── Token dependency ────────────────────────────────────────────────


def _require_internal_token(x_internal_token: str = Header(...)) -> None:
    """Validate the internal job token from the request header.

    Uses constant-time comparison to prevent timing attacks.
    Raises 403 if the token is empty or does not match the configured value.
    """
    expected = get_settings().internal_job_token
    if not expected or not secrets.compare_digest(x_internal_token, expected):
        logger.warning("Internal endpoint auth failed: invalid or missing token")
        raise HTTPException(status_code=403, detail="Invalid internal token")


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/run_scan")
async def run_scan(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    workspace_id: str | None = Query(
        None,
        description="Workspace ID; uses default if omitted (Phase 3)",
    ),
):
    """Trigger a full scan across all companies.

    When workspace_id provided (Phase 3), uses that workspace's active pack
    for analysis attribution. Omit for default workspace.
    Returns the completed JobRun summary.
    """
    from app.services.scan_orchestrator import run_scan_all

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None

    try:
        job = await run_scan_all(db, workspace_id=ws_id)
        return {
            "status": job.status,
            "job_run_id": job.id,
            "companies_processed": job.companies_processed,
        }
    except Exception as exc:
        logger.exception("Internal scan failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_briefing")
async def run_briefing(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    workspace_id: str | None = Query(
        None,
        description="Workspace ID; uses default if omitted (Phase 3)",
    ),
):
    """Trigger briefing generation for top companies.

    When workspace_id provided (Phase 3), generates briefing for that
    workspace's pack. Omit for default workspace.
    Returns the number of briefing items generated.
    """
    from app.services.briefing import generate_briefing

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None

    try:
        items = generate_briefing(db, workspace_id=ws_id)
        return {"status": "completed", "items_generated": len(items)}
    except Exception as exc:
        logger.exception("Internal briefing generation failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_score")
async def run_score(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    workspace_id: str | None = Query(None, description="Workspace ID; uses default if omitted"),
    pack_id: str | None = Query(
        None, description="Pack UUID; uses workspace active pack if omitted"
    ),
):
    """Trigger nightly TRS scoring (Issue #104).

    Scores all companies with SignalEvents in last 365 days or on watchlist.
    Returns job summary with companies_scored, companies_skipped.

    Idempotency: Pass X-Idempotency-Key to skip duplicate runs. Use
    workspace-scoped keys (e.g. ``{workspace_id}:{timestamp}``) to avoid
    collisions across workspaces.

    Pack resolution (Phase 3): When pack_id omitted, uses workspace's
    active_pack_id; falls back to default pack when workspace has none.
    """
    from uuid import UUID

    from app.pipeline.executor import run_stage

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    validate_uuid_param_or_422(pack_id, "pack_id")

    try:
        pack_uuid = UUID(pack_id.strip()) if pack_id and pack_id.strip() else None
        ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None
        result = run_stage(
            db,
            job_type="score",
            workspace_id=ws_id,
            pack_id=pack_uuid,
            idempotency_key=x_idempotency_key,
        )
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "companies_scored": result["companies_scored"],
            "companies_engagement": result.get("companies_engagement", 0),
            "companies_esl_suppressed": result.get("companies_esl_suppressed", 0),
            "companies_skipped": result["companies_skipped"],
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Internal score job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_alert_scan")
async def run_alert_scan_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    workspace_id: str | None = Query(
        None,
        description="Workspace ID; uses default if omitted (Issue #193).",
    ),
):
    """Trigger daily readiness delta alert scan (Issue #92).

    Run after score_nightly. Creates alerts when |delta| >= threshold.
    Snapshot reads are pack-scoped; pack resolved from workspace (Issue #193).
    Returns alerts_created, companies_scanned.
    """
    from app.pipeline.stages import DEFAULT_WORKSPACE_ID
    from app.services.pack_resolver import get_default_pack_id, get_pack_for_workspace
    from app.services.readiness.alert_scan import run_alert_scan

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    ws_id = (
        workspace_id.strip() if workspace_id and workspace_id.strip() else None
    ) or DEFAULT_WORKSPACE_ID
    pack_id = get_pack_for_workspace(db, ws_id) or get_default_pack_id(db)

    try:
        result = run_alert_scan(db, pack_id=pack_id)
        return {
            "status": result["status"],
            "alerts_created": result["alerts_created"],
            "companies_scanned": result["companies_scanned"],
        }
    except Exception as exc:
        logger.exception("Internal alert scan failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_derive")
async def run_derive_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    workspace_id: str | None = Query(None, description="Workspace ID; uses default if omitted"),
    pack_id: str | None = Query(
        None, description="Pack UUID; uses workspace active pack if omitted"
    ),
):
    """Trigger derive stage: populate signal_instances from SignalEvents (Phase 2).

    Run after ingest. Applies pack passthrough and pattern derivers. Idempotent.
    Pass X-Idempotency-Key to skip duplicate runs.
    Pack resolution: when pack_id omitted, uses workspace active_pack_id.
    """
    from uuid import UUID

    from app.pipeline.executor import run_stage

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    validate_uuid_param_or_422(pack_id, "pack_id")

    try:
        pack_uuid = UUID(pack_id.strip()) if pack_id and pack_id.strip() else None
        ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None
        result = run_stage(
            db,
            job_type="derive",
            workspace_id=ws_id,
            pack_id=pack_uuid,
            idempotency_key=x_idempotency_key,
        )
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "instances_upserted": result.get("instances_upserted", 0),
            "events_processed": result.get("events_processed", 0),
            "events_skipped": result.get("events_skipped", 0),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Internal derive job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_ingest")
async def run_ingest_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    workspace_id: str | None = Query(None, description="Workspace ID; uses default if omitted"),
    pack_id: str | None = Query(
        None, description="Pack UUID; uses workspace active pack if omitted"
    ),
):
    """Trigger daily ingestion (Issue #90).

    Fetches events since last run (or 24h ago), persists with deduplication.
    Returns job summary with inserted, skipped_duplicate, skipped_invalid.

    Idempotency: Pass X-Idempotency-Key to skip duplicate runs. Use
    workspace-scoped keys (e.g. ``{workspace_id}:{timestamp}``) to avoid
    collisions across workspaces.
    Pack resolution: when pack_id omitted, uses workspace active_pack_id.
    Ingested events are written to the resolved pack (Phase 3).
    """
    from uuid import UUID

    from app.pipeline.executor import run_stage

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    validate_uuid_param_or_422(pack_id, "pack_id")

    try:
        pack_uuid = UUID(pack_id.strip()) if pack_id and pack_id.strip() else None
        ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None
        result = run_stage(
            db,
            job_type="ingest",
            workspace_id=ws_id,
            pack_id=pack_uuid,
            idempotency_key=x_idempotency_key,
        )
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "inserted": result["inserted"],
            "skipped_duplicate": result["skipped_duplicate"],
            "skipped_invalid": result["skipped_invalid"],
            "errors_count": result["errors_count"],
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Internal ingest job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_update_lead_feed")
async def run_update_lead_feed_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    workspace_id: str | None = Query(None, description="Workspace ID; uses default if omitted"),
    pack_id: str | None = Query(
        None, description="Pack UUID; uses workspace active pack if omitted"
    ),
    as_of: date | None = Query(
        None,
        description="Snapshot date (YYYY-MM-DD). Default: today.",
    ),
):
    """Trigger lead_feed projection update (Phase 1, Issue #225, ADR-004).

    Builds projection from ReadinessSnapshot + EngagementSnapshot for as_of.
    Run after score. Idempotent. Pack resolution: when pack_id omitted,
    uses workspace active_pack_id.
    """
    from uuid import UUID

    from app.pipeline.executor import run_stage

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    validate_uuid_param_or_422(pack_id, "pack_id")

    try:
        pack_uuid = UUID(pack_id.strip()) if pack_id and pack_id.strip() else None
        ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None
        result = run_stage(
            db,
            job_type="update_lead_feed",
            workspace_id=ws_id,
            pack_id=pack_uuid,
            idempotency_key=x_idempotency_key,
            as_of=as_of,
        )
        return {
            "status": result["status"],
            "job_run_id": result.get("job_run_id"),
            "rows_upserted": result.get("rows_upserted", 0),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Internal update_lead_feed job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_backfill_lead_feed")
async def run_backfill_lead_feed_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    as_of: date | None = Query(
        None,
        description="Snapshot date (YYYY-MM-DD). Default: today.",
    ),
):
    """Backfill lead_feed for all workspaces (Phase 3, Issue #225).

    Runs build_lead_feed_from_snapshots for each workspace with a resolved pack.
    Idempotent: safe to re-run.
    """
    from app.services.lead_feed.run_update import run_backfill_lead_feed

    try:
        result = run_backfill_lead_feed(db, as_of=as_of)
        return {
            "status": result["status"],
            "workspaces_processed": result["workspaces_processed"],
            "total_rows_upserted": result["total_rows_upserted"],
            "errors": result.get("errors"),
        }
    except Exception as exc:
        logger.exception("Internal backfill_lead_feed job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_daily_aggregation")
async def run_daily_aggregation_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    workspace_id: str | None = Query(None, description="Workspace ID; uses default if omitted"),
    pack_id: str | None = Query(
        None, description="Pack UUID; uses workspace active pack if omitted"
    ),
):
    """Trigger daily aggregation: ingest → derive → score (Issue #246).

    Unified entry point for cron. Returns status, job_run_id, inserted,
    companies_scored, ranked_count, ranked_companies, error. Idempotent with X-Idempotency-Key.

    ranked_count: count of all companies with any readiness score for today
    (outreach_score_threshold=0 is applied by the orchestrator). This is the
    monitoring population; it is NOT filtered by the configured outreach threshold.
    The briefing view (/api/briefing) applies its own threshold independently.

    ranked_companies: list of all scored companies in rank order. Each item has:
    - company_name (str): company display name
    - composite (int | float): readiness composite score
    - band (str): ESL/engagement band (e.g. allow, block, nurture)
    """
    from uuid import UUID

    from app.pipeline.executor import run_stage

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    validate_uuid_param_or_422(pack_id, "pack_id")

    try:
        pack_uuid = UUID(pack_id.strip()) if pack_id and pack_id.strip() else None
        ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None
        result = run_stage(
            db,
            job_type="daily_aggregation",
            workspace_id=ws_id,
            pack_id=pack_uuid,
            idempotency_key=x_idempotency_key,
        )
        inserted = result.get("ingest_result", {}).get("inserted", result.get("inserted", 0))
        companies_scored = result.get("score_result", {}).get(
            "companies_scored", result.get("companies_scored", 0)
        )
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "inserted": inserted,
            "companies_scored": companies_scored,
            "ranked_count": result.get("ranked_count", 0),
            "ranked_companies": result.get("ranked_companies", []),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Internal daily aggregation job failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_watchlist_seed")
async def run_watchlist_seed_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    body: SeedFromBundlesRequest = ...,
    pack_id: str | None = Query(
        None, description="Pack UUID; uses workspace active pack if omitted"
    ),
):
    """Trigger watchlist seed flow: seed from bundles → derive → score (Issue #279 M3).

    Body: bundle_ids (required), optional workspace_id. When MULTI_WORKSPACE_ENABLED
    is true, workspace_id is required to enforce tenant boundaries (bundles are
    loaded workspace-scoped). Optional pack_id query uses workspace active pack
    when omitted. Returns status, seed_result, derive_result, score_result.

    Idempotency: Pass X-Idempotency-Key to skip duplicate runs. Use
    workspace-scoped keys (e.g. ``{workspace_id}:{timestamp}``) to avoid
    collisions across workspaces.
    """
    from uuid import UUID

    from app.pipeline.executor import run_stage
    from app.pipeline.stages import DEFAULT_WORKSPACE_ID

    settings = get_settings()
    if settings.multi_workspace_enabled and body.workspace_id is None:
        raise HTTPException(
            status_code=422,
            detail="workspace_id is required when MULTI_WORKSPACE_ENABLED is true to enforce tenant boundaries",
        )

    validate_uuid_param_or_422(pack_id, "pack_id")
    pack_uuid = UUID(pack_id.strip()) if pack_id and pack_id.strip() else None
    ws_id = str(body.workspace_id) if body.workspace_id is not None else DEFAULT_WORKSPACE_ID

    try:
        result = run_stage(
            db,
            job_type="watchlist_seed",
            workspace_id=ws_id,
            pack_id=pack_uuid,
            idempotency_key=x_idempotency_key,
            bundle_ids=body.bundle_ids,
        )
        return {
            "status": result["status"],
            "job_run_id": result.get("job_run_id"),
            "seed_result": result["seed_result"],
            "derive_result": result["derive_result"],
            "score_result": result["score_result"],
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        if "Unknown job_type" in str(exc):
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        raise
    except Exception as exc:
        logger.exception("Internal run_watchlist_seed failed")
        return {"status": "failed", "error": str(exc)}


@router.post("/run_monitor")
async def run_monitor_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    workspace_id: str | None = Query(
        None,
        description="Workspace ID; uses default if omitted (Phase 3)",
    ),
    company_ids: str | None = Query(
        None,
        description="Optional comma-separated company IDs (e.g. 1,2,3). If omitted, all companies with website_url.",
    ),
):
    """Trigger diff-based monitor: fetch → snapshots → diff → LLM interpret → persist (M6, Issue #280).

    Robots-aware fetch of blog, careers, press, pricing, docs/changelog; detects changes,
    interprets via LLM, validates against core taxonomy, and persists candidates as
    SignalEvents with source='page_monitor'. Requires X-Internal-Token.

    Returns status, change_events_count, events_stored, events_skipped_duplicate,
    companies_processed.
    """
    from app.monitor.runner import run_monitor_full

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    ws_id = workspace_id.strip() if workspace_id and workspace_id.strip() else None

    company_ids_list: list[int] | None = None
    if company_ids and company_ids.strip():
        try:
            company_ids_list = [int(x.strip()) for x in company_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="company_ids must be comma-separated integers",
            ) from None

    try:
        result = await run_monitor_full(
            db,
            workspace_id=ws_id,
            company_ids=company_ids_list,
        )
        return {
            "status": result["status"],
            "change_events_count": result["change_events_count"],
            "events_stored": result["events_stored"],
            "events_skipped_duplicate": result["events_skipped_duplicate"],
            "companies_processed": result["companies_processed"],
        }
    except Exception as exc:
        logger.exception("Internal run_monitor failed")
        return {
            "status": "failed",
            "change_events_count": 0,
            "events_stored": 0,
            "events_skipped_duplicate": 0,
            "companies_processed": 0,
            "error": str(exc),
        }


@router.get("/scout_analytics", response_model=ScoutAnalyticsResponse)
def scout_analytics_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    workspace_id: str = Query(
        ...,
        min_length=1,
        description="Workspace ID (required for tenant scoping)",
    ),
    since: date | None = Query(
        None,
        description="Return only runs started on or after this date (YYYY-MM-DD, UTC)",
    ),
) -> ScoutAnalyticsResponse:
    """Return aggregate scout yield metrics for a workspace (M5, Issue #282).

    Read-only. Reads from scout_runs and scout_evidence_bundles filtered by
    workspace_id; optional since filters by run started_at. Response includes
    runs_count, total_bundles, and optional by_family from config_snapshot.
    Requires X-Internal-Token.
    """
    validate_uuid_param_or_422(workspace_id, "workspace_id")
    from uuid import UUID

    from app.services.scout.scout_analytics import get_scout_analytics

    try:
        ws_uuid = UUID(workspace_id.strip())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid workspace_id: must be a valid UUID",
        ) from None
    result = get_scout_analytics(db, workspace_id=ws_uuid, since=since)
    return result


@router.post("/run_scout")
async def run_scout_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    body: RunScoutRequest = ...,
):
    """Trigger LLM Discovery Scout (Evidence-Only). Returns run_id, bundles_count, status.

    Body: icp_definition, workspace_id (required for tenant scoping), optional exclusion_rules,
    optional pack_id, optional page_fetch_limit.
    Does not write to companies or signal_events; output is stored in scout_runs, scout_evidence_bundles,
    and the Evidence Store (evidence_bundles, evidence_sources, etc.).
    """
    from app.services.scout.discovery_scout_service import run as run_scout

    try:
        run_id, bundles, _metadata = await run_scout(
            db,
            icp_definition=body.icp_definition,
            exclusion_rules=body.exclusion_rules,
            pack_id=body.pack_id,
            page_fetch_limit=body.page_fetch_limit,
            workspace_id=body.workspace_id,
        )
        return {
            "run_id": run_id,
            "bundles_count": len(bundles),
            "status": "completed",
            "error": None,
        }
    except Exception as exc:
        logger.exception("Internal run_scout failed")
        return {"status": "failed", "run_id": "", "bundles_count": 0, "error": str(exc)}


@router.get("/scout_runs", response_model=ScoutRunListResponse)
async def list_scout_runs(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    workspace_id: str = Query(
        ..., description="Workspace ID (required). Lists only runs for this tenant."
    ),
):
    """List scout runs for a workspace. workspace_id is required for tenant scoping.

    Returns runs ordered by started_at descending. No cross-tenant data.
    """
    from uuid import UUID

    from app.models.scout_run import ScoutRun

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    ws_uuid = UUID(workspace_id.strip())
    runs = (
        db.query(ScoutRun)
        .filter(ScoutRun.workspace_id == ws_uuid)
        .order_by(ScoutRun.started_at.desc())
        .all()
    )
    items = [
        ScoutRunListItem(
            run_id=str(r.run_id),
            started_at=r.started_at,
            status=r.status,
            bundles_count=len(r.bundles),
        )
        for r in runs
    ]
    return ScoutRunListResponse(workspace_id=workspace_id.strip(), runs=items)


@router.post("/evidence/store")
async def store_evidence_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    body: StoreEvidenceRequest = ...,
):
    """Persist Scout-run result to Evidence Store (testing / external Scout runner).

    Body: run_id, bundles, metadata (ScoutRunMetadata), optional run_context, optional raw_model_output.
    M6: optional run_verification; when True, verify_bundles runs first, failures are quarantined
    with reason_codes, only passing bundles are stored. Optional structured_payloads (length must
    match bundles when run_verification=True). Requires X-Internal-Token. Returns stored_count and
    bundle_ids; when run_verification was used, quarantined_count is also returned.
    """
    from fastapi import HTTPException

    from app.evidence.store import quarantine_verification_failure, store_evidence_bundle
    from app.verification import verify_bundles

    try:
        run_context = body.run_context if body.run_context is not None else {"run_id": body.run_id}
        bundles_to_store = body.bundles
        structured_payloads_to_store = None
        quarantined_count = 0

        if body.run_verification and body.bundles:
            if body.structured_payloads is not None and len(body.structured_payloads) != len(
                body.bundles
            ):
                raise HTTPException(
                    status_code=422,
                    detail="structured_payloads length must match bundles when run_verification=True",
                )
            structured_payloads_for_verify = (
                body.structured_payloads
                if body.structured_payloads is not None
                else [None] * len(body.bundles)
            )
            results = verify_bundles(body.bundles, structured_payloads_for_verify)
            for i, result in enumerate(results):
                if not result.passed:
                    quarantine_verification_failure(
                        db,
                        run_id=body.run_id,
                        bundle_index=i,
                        bundle_dict=body.bundles[i].model_dump(mode="json"),
                        structured_payload=structured_payloads_for_verify[i],
                        reason_codes=result.reason_codes,
                    )
                    quarantined_count += 1
            passing_indices = [i for i, r in enumerate(results) if r.passed]
            bundles_to_store = [body.bundles[i] for i in passing_indices]
            if body.structured_payloads is not None:
                structured_payloads_to_store = [
                    body.structured_payloads[i] for i in passing_indices
                ]
            elif passing_indices:
                structured_payloads_to_store = [None] * len(passing_indices)

        records = store_evidence_bundle(
            db,
            run_id=body.run_id,
            scout_version=body.metadata.model_version,
            bundles=bundles_to_store,
            run_context=run_context,
            raw_model_output=body.raw_model_output,
            structured_payloads=structured_payloads_to_store,
            pack_id=None,
        )
        db.commit()
        out: dict = {
            "status": "completed",
            "stored_count": len(records),
            "bundle_ids": [str(r.id) for r in records],
            "error": None,
        }
        if body.run_verification:
            out["quarantined_count"] = quarantined_count
        return out
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Internal evidence store failed")
        db.rollback()
        return {
            "status": "failed",
            "stored_count": 0,
            "bundle_ids": [],
            "error": str(exc),
        }


@router.get("/evidence/bundles")
async def list_evidence_bundles_for_workspace(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    run_id: str = Query(..., min_length=1, max_length=64),
    workspace_id: uuid.UUID = Query(...),
):
    """List evidence bundles for a run_id, only if the run belongs to workspace_id.

    Returns [] when run does not exist or belongs to another workspace (no cross-tenant leak).
    Requires X-Internal-Token.
    """
    from app.evidence.repository import list_bundles_by_run_for_workspace

    bundles = list_bundles_by_run_for_workspace(db, run_id, workspace_id)
    return {
        "bundles": [b.model_dump(mode="json") for b in bundles],
        "count": len(bundles),
    }


@router.get("/evidence/quarantine")
async def list_evidence_quarantine(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    limit: int = Query(100, ge=1, le=500, description="Max entries to return"),
    offset: int = Query(0, ge=0, description="Skip this many entries"),
    reason_substring: str | None = Query(
        None,
        description="Filter by reason (case-insensitive substring)",
    ),
    since: datetime | None = Query(
        None,
        description="Return only entries created on or after this time (ISO 8601)",
    ),
):
    """List quarantined evidence entries (M4, Issue #278). Requires X-Internal-Token.

    Payload can contain run context, bundle content, company names, and snippets;
    intended only for internal/cron use.
    """
    from app.evidence.quarantine_repository import list_quarantine

    entries = list_quarantine(
        db,
        limit=limit,
        offset=offset,
        reason_substring=reason_substring,
        since=since,
    )
    return {
        "entries": [e.model_dump(mode="json") for e in entries],
        "count": len(entries),
    }


@router.get("/evidence/quarantine/{quarantine_id}")
async def get_evidence_quarantine(
    quarantine_id: uuid.UUID,
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
):
    """Get one quarantined evidence entry by id (M4, Issue #278). Returns 404 if not found. Requires X-Internal-Token.

    Payload can contain run context, bundle content, company names, and snippets;
    intended only for internal/cron use.
    """
    from app.evidence.quarantine_repository import get_quarantine

    entry = get_quarantine(db, quarantine_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Quarantine entry not found")
    return entry.model_dump(mode="json")


@router.post("/run_bias_audit")
async def run_bias_audit_endpoint(
    db: Session = Depends(get_db),
    _token: None = Depends(_require_internal_token),
    month: date | None = Query(
        None,
        description="Report month (YYYY-MM-DD, first day). Default: previous month.",
    ),
    workspace_id: str | None = Query(
        None,
        description="Workspace ID; uses default if omitted (Issue #193).",
    ),
):
    """Trigger monthly bias audit (Issue #112).

    Analyzes surfaced companies for funding, alignment, stage skew.
    Persists report keyed by (report_month, pack_id); flags when any segment > 70%.
    When workspace_id is provided, audit is scoped to that workspace's pack (Issue #193).
    """
    from app.pipeline.stages import DEFAULT_WORKSPACE_ID
    from app.services.bias_audit import run_bias_audit

    validate_uuid_param_or_422(workspace_id, "workspace_id")
    ws_id = (
        workspace_id.strip() if workspace_id and workspace_id.strip() else None
    ) or DEFAULT_WORKSPACE_ID

    try:
        report_month = month
        if report_month is not None:
            report_month = report_month.replace(day=1)
        result = run_bias_audit(db, report_month=report_month, workspace_id=ws_id)
        return {
            "status": result["status"],
            "job_run_id": result["job_run_id"],
            "report_id": result.get("report_id"),
            "surfaced_count": result.get("surfaced_count", 0),
            "flags": result.get("flags", []),
            "error": result.get("error"),
        }
    except Exception as exc:
        logger.exception("Internal bias audit failed")
        return {"status": "failed", "error": str(exc)}
