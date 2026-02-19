"""Outreach API routes (Issue #108)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_auth
from app.config import get_settings
from app.db.session import get_db
from app.schemas.outreach import OutreachReviewItem, OutreachReviewResponse
from app.services.outreach_review import (
    get_latest_snapshot_date,
    get_weekly_review_companies,
)

router = APIRouter()

# Max override for limit query param
MAX_REVIEW_LIMIT = 20


@router.get("/review", response_model=OutreachReviewResponse)
def api_outreach_review(
    date_param: date | None = Query(None, alias="date", description="Snapshot date (YYYY-MM-DD). Default: latest available."),
    limit: int | None = Query(None, ge=1, le=MAX_REVIEW_LIMIT, description="Max companies to return. Default: weekly_review_limit."),
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
