"""Briefing page HTML routes."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_ui_auth
from app.config import get_settings
from app.models.briefing_item import BriefingItem
from app.models.company import Company
from app.models.engagement_snapshot import EngagementSnapshot
from app.models.job_run import JobRun
from app.models.readiness_snapshot import ReadinessSnapshot
from app.models.user import User
from app.services.briefing import get_emerging_companies_for_briefing
from app.services.esl.esl_engine import compute_outreach_score
from app.services.esl.esl_gate_filter import (
    get_effective_engagement_type,
    is_suppressed_from_engagement,
)
from app.services.pack_resolver import get_default_pack_id
from app.services.readiness.human_labels import event_type_to_label
from app.services.scoring import get_display_scores_for_companies

logger = logging.getLogger(__name__)

router = APIRouter()

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/briefing", response_class=HTMLResponse)
def briefing_today(
    request: Request,
    user: User = Depends(require_ui_auth),
    db: Session = Depends(get_db),
):
    """Show today's briefing page."""
    today = date.today()
    return _render_briefing(request, db, today, user)


@router.get("/briefing/{date_str}", response_class=HTMLResponse)
def briefing_by_date(
    request: Request,
    date_str: str,
    user: User = Depends(require_ui_auth),
    db: Session = Depends(get_db),
):
    """Show briefing for a specific date (YYYY-MM-DD)."""
    try:
        briefing_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse(url="/briefing", status_code=302)
    return _render_briefing(request, db, briefing_date, user)


@router.post("/briefing/generate")
def briefing_generate(
    request: Request,
    user: User = Depends(require_ui_auth),
    db: Session = Depends(get_db),
):
    """Trigger briefing generation and redirect to briefing page (issue #32)."""
    try:
        from app.services.briefing import generate_briefing

        generate_briefing(db)
        # Check for partial failures (issue #32)
        latest = (
            db.query(JobRun)
            .filter(JobRun.job_type == "briefing")
            .order_by(JobRun.started_at.desc())
            .first()
        )
        if latest and latest.error_message:
            return RedirectResponse(
                url="/briefing?error=Partial+failures.+See+Settings+for+details",
                status_code=303,
            )
        return RedirectResponse(url="/briefing", status_code=303)
    except ImportError:
        logger.warning("Briefing service not available yet")
        return RedirectResponse(
            url="/briefing?error=Briefing+service+not+available+yet",
            status_code=303,
        )
    except Exception as exc:
        logger.exception("Briefing generation failed: %s", exc)
        return RedirectResponse(
            url="/briefing?error=Briefing+generation+failed",
            status_code=303,
        )


# Sort options for briefing (Issue #24, #103)
_SORT_SCORE = "score"
_SORT_RECENT = "recent"
_SORT_OUTREACH = "outreach"
_SORT_OUTREACH_SCORE = "outreach_score"
_VALID_SORTS = frozenset({_SORT_SCORE, _SORT_RECENT, _SORT_OUTREACH, _SORT_OUTREACH_SCORE})


def get_briefing_data(
    db: Session,
    briefing_date: date,
    sort: str = _SORT_SCORE,
) -> dict:
    """Fetch briefing data for a date (Issue #110). Shared by HTML and JSON API.

    Returns dict with: items, emerging_companies, display_scores, esl_by_company.

    TODO(multi-tenant): Scope by workspace_id when multi-workspace is enabled;
    get_emerging_companies and pack_id resolution should use workspace active pack.
    """
    if sort not in _VALID_SORTS:
        sort = _SORT_SCORE

    base_query = (
        db.query(BriefingItem)
        .options(joinedload(BriefingItem.company), joinedload(BriefingItem.analysis))
        .filter(BriefingItem.briefing_date == briefing_date)
        .join(Company, BriefingItem.company_id == Company.id)
    )

    if sort == _SORT_SCORE:
        base_query = base_query.order_by(Company.cto_need_score.desc().nulls_last())
    elif sort == _SORT_RECENT:
        base_query = base_query.order_by(
            Company.last_scan_at.desc().nulls_last()
        )
    elif sort == _SORT_OUTREACH_SCORE:
        base_query = base_query.order_by(BriefingItem.id.asc())
    else:
        base_query = base_query.order_by(BriefingItem.created_at.desc())

    raw_items = base_query.all()

    seen: set[int] = set()
    items: list[BriefingItem] = []
    for item in raw_items:
        if item.company_id not in seen:
            seen.add(item.company_id)
            items.append(item)

    esl_by_company: dict[int, dict] = {}
    pack_id = get_default_pack_id(db)
    if items and pack_id is not None:
        company_ids = [item.company_id for item in items]
        pack_match = or_(
            ReadinessSnapshot.pack_id == EngagementSnapshot.pack_id,
            (ReadinessSnapshot.pack_id.is_(None)) & (EngagementSnapshot.pack_id.is_(None)),
        )
        pack_filter = or_(
            ReadinessSnapshot.pack_id == pack_id,
            ReadinessSnapshot.pack_id.is_(None),
        )
        pairs = (
            db.query(ReadinessSnapshot, EngagementSnapshot)
            .join(EngagementSnapshot, (ReadinessSnapshot.company_id == EngagementSnapshot.company_id) & (ReadinessSnapshot.as_of == EngagementSnapshot.as_of) & pack_match)
            .filter(
                ReadinessSnapshot.company_id.in_(company_ids),
                ReadinessSnapshot.as_of == briefing_date,
                pack_filter,
            )
            .all()
        )
        suppressed_company_ids: set[int] = set()
        for rs, es in pairs:
            if is_suppressed_from_engagement(es.esl_decision, es.explain):
                suppressed_company_ids.add(rs.company_id)
                continue
            effective_type = get_effective_engagement_type(
                es.engagement_type, es.explain, es.esl_decision
            )
            esl_decision = es.esl_decision or (es.explain or {}).get("esl_decision")
            sensitivity_level = es.sensitivity_level or (es.explain or {}).get(
                "sensitivity_level"
            )
            esl_by_company[rs.company_id] = {
                "esl_score": es.esl_score,
                "outreach_score": compute_outreach_score(rs.composite, es.esl_score),
                "engagement_type": effective_type,
                "cadence_blocked": es.cadence_blocked,
                "stability_cap_triggered": (es.explain or {}).get(
                    "stability_cap_triggered", False
                ),
                "esl_decision": esl_decision,
                "sensitivity_level": sensitivity_level,
            }
        # Filter items: exclude companies with esl_decision == "suppress" (Issue #175)
        items = [i for i in items if i.company_id not in suppressed_company_ids]
        if sort == _SORT_OUTREACH_SCORE:
            items.sort(
                key=lambda i: esl_by_company.get(i.company_id, {}).get(
                    "outreach_score", -1
                ),
                reverse=True,
            )

    display_scores: dict[int, int] = {}
    if items:
        company_ids = [item.company_id for item in items]
        display_scores = get_display_scores_for_companies(db, company_ids)

    settings = get_settings()
    emerging_triples = get_emerging_companies_for_briefing(
        db,
        briefing_date,
        limit=settings.weekly_review_limit,
        outreach_score_threshold=settings.outreach_score_threshold,
    )
    emerging_companies: list[dict] = []
    for readiness_snap, engagement_snap, company in emerging_triples:
        top_events = (readiness_snap.explain or {}).get("top_events") or []
        top_signals = [
            event_type_to_label(ev.get("event_type", ""))
            for ev in top_events[:3]
        ]
        outreach_score = compute_outreach_score(
            readiness_snap.composite, engagement_snap.esl_score
        )
        effective_type = get_effective_engagement_type(
            engagement_snap.engagement_type,
            engagement_snap.explain,
            engagement_snap.esl_decision,
        )
        esl_decision = engagement_snap.esl_decision or (
            engagement_snap.explain or {}
        ).get("esl_decision")
        sensitivity_level = engagement_snap.sensitivity_level or (
            engagement_snap.explain or {}
        ).get("sensitivity_level")
        emerging_companies.append({
            "company": company,
            "snapshot": readiness_snap,
            "engagement_snapshot": engagement_snap,
            "outreach_score": outreach_score,
            "esl_score": engagement_snap.esl_score,
            "engagement_type": effective_type,
            "cadence_blocked": engagement_snap.cadence_blocked,
            "stability_cap_triggered": (engagement_snap.explain or {}).get(
                "stability_cap_triggered", False
            ),
            "esl_decision": esl_decision,
            "sensitivity_level": sensitivity_level,
            "top_signals": top_signals,
        })

    return {
        "items": items,
        "emerging_companies": emerging_companies,
        "display_scores": display_scores,
        "esl_by_company": esl_by_company,
    }


def _render_briefing(
    request: Request,
    db: Session,
    briefing_date: date,
    user: User,
) -> HTMLResponse:
    """Query briefing items for a date and render the template."""
    sort = request.query_params.get("sort", _SORT_SCORE)
    data = get_briefing_data(db, briefing_date, sort)
    items = data["items"]
    emerging_companies = data["emerging_companies"]
    display_scores = data["display_scores"]
    esl_by_company = data["esl_by_company"]

    today = date.today()
    prev_date = (briefing_date - timedelta(days=1)).isoformat()
    next_date = (briefing_date + timedelta(days=1)).isoformat() if briefing_date < today else None

    # Base path for sort links (preserve date when viewing specific date)
    briefing_path = "/briefing" if briefing_date == today else f"/briefing/{briefing_date.isoformat()}"

    # Check for error flash from query params
    error = request.query_params.get("error")

    # Latest briefing job for failure alert (issue #32)
    latest_briefing_job = (
        db.query(JobRun)
        .filter(JobRun.job_type == "briefing")
        .order_by(JobRun.started_at.desc())
        .first()
    )
    job_has_failures = (
        latest_briefing_job is not None
        and (
            latest_briefing_job.status == "failed"
            or (latest_briefing_job.error_message or "").strip() != ""
        )
    )

    return templates.TemplateResponse(
        request,
        "briefing/today.html",
        {
            "items": items,
            "briefing_date": briefing_date,
            "today": today,
            "prev_date": prev_date,
            "next_date": next_date,
            "user": user,
            "flash_message": error,
            "flash_type": "error" if error else None,
            "display_scores": display_scores,
            "sort": sort,
            "briefing_path": briefing_path,
            "job_has_failures": job_has_failures,
            "emerging_companies": emerging_companies,
            "esl_by_company": esl_by_company,
        },
    )

