"""Outreach API routes (Issue #108, #122)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_auth, require_workspace_access, validate_uuid_param_or_422
from app.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.schemas.outreach import (
    OutreachRecommendationResponse,
    OutreachReviewItem,
    OutreachReviewResponse,
    ore_recommendation_to_response,
)
from app.services.esl.engagement_snapshot_writer import compute_esl_from_context
from app.services.ore.ore_pipeline import get_or_create_ore_recommendation
from app.services.outreach_review import (
    get_latest_snapshot_date,
    get_weekly_review_companies,
)

router = APIRouter()

# Max override for limit query param
MAX_REVIEW_LIMIT = 20


@router.get("/review", response_model=OutreachReviewResponse)
def api_outreach_review(
    date_param: date | None = Query(
        None, alias="date", description="Snapshot date (YYYY-MM-DD). Default: latest available."
    ),
    limit: int | None = Query(
        None,
        ge=1,
        le=MAX_REVIEW_LIMIT,
        description="Max companies to return. Default: weekly_review_limit.",
    ),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> OutreachReviewResponse:
    """Get top OutreachScore companies for weekly review (Issue #108).

    Returns companies sorted by OutreachScore DESC, excluding cooldown companies.
    Each company appears at most once. Includes explain block per company.
    """
    settings = get_settings()
    as_of = date_param
    if as_of is None:
        as_of = get_latest_snapshot_date(db)
        if as_of is None:
            as_of = date.today()

    effective_limit = limit if limit is not None else settings.weekly_review_limit
    effective_limit = min(effective_limit, MAX_REVIEW_LIMIT)

    items_raw = get_weekly_review_companies(
        db,
        as_of,
        limit=effective_limit,
        outreach_score_threshold=settings.outreach_score_threshold,
    )

    companies = [
        OutreachReviewItem(
            company_id=item["company_id"],
            company_name=item["company"].name or "",
            website_url=item["company"].website_url,
            outreach_score=item["outreach_score"],
            explain=item["explain"],
        )
        for item in items_raw
    ]

    return OutreachReviewResponse(as_of=as_of, companies=companies)


@router.get(
    "/recommendation/{company_id}",
    response_model=OutreachRecommendationResponse,
    status_code=status.HTTP_200_OK,
)
def api_outreach_recommendation(
    company_id: int,
    as_of: date | None = Query(
        None,
        alias="as_of",
        description="Snapshot date (YYYY-MM-DD). Default: latest available.",
    ),
    pack_id: UUID | None = Query(None, description="Pack ID. Default: workspace or app default."),
    workspace_id: str | None = Query(
        None,
        description="Workspace ID for pack resolution when pack_id omitted. Optional; when multi_workspace_enabled, defaults to default workspace if omitted.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
) -> OutreachRecommendationResponse:
    """Get ORE recommendation kit for a company (Issue #122 M2).

    Returns recommended playbook ID, draft variants, rationale, sensitivity tag, and
    core recommendation fields. Resolves as_of to latest snapshot date when omitted.
    Returns 404 when company or snapshot/recommendation not found.
    When multi_workspace_enabled, workspace access is enforced; effective workspace
    is used for pack resolution when pack_id is omitted.
    """
    settings = get_settings()
    if workspace_id is not None:
        validate_uuid_param_or_422(workspace_id, "workspace_id")
    effective_workspace_id: str | None = None
    if settings.multi_workspace_enabled:
        effective_workspace_id = workspace_id or DEFAULT_WORKSPACE_ID
        require_workspace_access(db, user, effective_workspace_id)
    else:
        effective_workspace_id = workspace_id

    resolved_as_of = as_of
    if resolved_as_of is None:
        resolved_as_of = get_latest_snapshot_date(db)
        if resolved_as_of is None:
            resolved_as_of = date.today()

    rec = get_or_create_ore_recommendation(
        db,
        company_id=company_id,
        as_of=resolved_as_of,
        pack_id=pack_id,
        workspace_id=effective_workspace_id,
    )
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company or snapshot not found; no recommendation available.",
        )

    sensitivity_tag: str | None = None
    if rec.pack_id is not None:
        ctx = compute_esl_from_context(
            db,
            company_id=company_id,
            as_of=resolved_as_of,
            pack_id=rec.pack_id,
        )
        if ctx is not None:
            sensitivity_tag = ctx.get("sensitivity_level") if isinstance(ctx.get("sensitivity_level"), str) else None

    return ore_recommendation_to_response(rec, sensitivity_tag=sensitivity_tag)
