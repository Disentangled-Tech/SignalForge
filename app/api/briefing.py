"""Briefing JSON API routes (Issue #110)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.briefing_views import get_briefing_data
from app.api.deps import get_db, require_auth, validate_uuid_param_or_422
from app.config import get_settings
from app.schemas.briefing import (
    BriefingItemRead,
    BriefingResponse,
    EmergingCompanyBriefing,
)
from app.services.company import _model_to_read

router = APIRouter()


def _item_to_read(item, display_scores: dict, esl_by_company: dict) -> BriefingItemRead:
    """Build BriefingItemRead from BriefingItem with optional ESL fields."""
    company_read = _model_to_read(item.company)
    stage = (
        (item.analysis.stage if item.analysis else None)
        or (item.company.current_stage if item.company else None)
    )

    esl = esl_by_company.get(item.company_id) or {}
    return BriefingItemRead(
        id=item.id,
        company=company_read,
        stage=stage,
        why_now=item.why_now,
        risk_summary=item.risk_summary,
        suggested_angle=item.suggested_angle,
        outreach_subject=item.outreach_subject,
        outreach_message=item.outreach_message,
        briefing_date=item.briefing_date or date.today(),
        created_at=item.created_at,
        esl_score=esl.get("esl_score"),
        outreach_score=esl.get("outreach_score"),
        outreach_recommendation=esl.get("engagement_type"),
        cadence_blocked=esl.get("cadence_blocked"),
        stability_cap_triggered=esl.get("stability_cap_triggered"),
        esl_decision=esl.get("esl_decision"),
        sensitivity_level=esl.get("sensitivity_level"),
    )


@router.get("/daily", response_model=BriefingResponse)
def api_briefing_daily(
    date_param: date | None = Query(
        None,
        alias="date",
        description="Briefing date (YYYY-MM-DD). Default: today.",
    ),
    sort: str = Query(
        "score",
        description="Sort order: score, recent, outreach, outreach_score",
    ),
    workspace_id: str | None = Query(
        None,
        description="Workspace ID (when multi_workspace_enabled). Default workspace if omitted.",
    ),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> BriefingResponse:
    """Get daily briefing as JSON (Issue #110).

    Returns briefing items and emerging companies with ESL score, outreach
    recommendation, stability flags, and cooldown flags.

    When multi_workspace_enabled, pass workspace_id to scope emerging companies.
    Invalid workspace_id returns 422.
    """
    briefing_date = date_param if date_param is not None else date.today()
    settings = get_settings()
    ws_id = workspace_id if settings.multi_workspace_enabled else None
    if ws_id is not None:
        validate_uuid_param_or_422(ws_id, "workspace_id")
    data = get_briefing_data(db, briefing_date, sort, workspace_id=ws_id)

    items = [
        _item_to_read(
            item,
            data["display_scores"],
            data["esl_by_company"],
        )
        for item in data["items"]
    ]

    emerging = [
        EmergingCompanyBriefing(
            company_id=ec["company"].id,
            company_name=ec["company"].name or "",
            website_url=ec["company"].website_url,
            outreach_score=ec["outreach_score"],
            esl_score=ec["esl_score"],
            engagement_type=ec["engagement_type"],
            cadence_blocked=ec["cadence_blocked"],
            stability_cap_triggered=ec["stability_cap_triggered"],
            top_signals=ec["top_signals"],
            trs=ec["snapshot"].composite if ec.get("snapshot") else None,
            momentum=ec["snapshot"].momentum if ec.get("snapshot") else None,
            complexity=ec["snapshot"].complexity if ec.get("snapshot") else None,
            pressure=ec["snapshot"].pressure if ec.get("snapshot") else None,
            leadership_gap=ec["snapshot"].leadership_gap if ec.get("snapshot") else None,
            esl_decision=ec.get("esl_decision"),
            sensitivity_level=ec.get("sensitivity_level"),
            recommendation_band=ec.get("recommendation_band"),
        )
        for ec in data["emerging_companies"]
    ]

    return BriefingResponse(
        date=briefing_date,
        items=items,
        emerging_companies=emerging,
        total=len(items),
    )
