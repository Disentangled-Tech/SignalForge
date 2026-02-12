"""Briefing page HTML routes."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_auth
from app.models.briefing_item import BriefingItem
from app.models.company import Company
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/briefing", response_class=HTMLResponse)
def briefing_today(
    request: Request,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Show today's briefing page."""
    today = date.today()
    return _render_briefing(request, db, today, user)


@router.get("/briefing/{date_str}", response_class=HTMLResponse)
def briefing_by_date(
    request: Request,
    date_str: str,
    user: User = Depends(require_auth),
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
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Trigger briefing generation and redirect to briefing page."""
    try:
        from app.services.briefing import generate_briefing

        generate_briefing(db)
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


def _render_briefing(
    request: Request,
    db: Session,
    briefing_date: date,
    user: User,
) -> HTMLResponse:
    """Query briefing items for a date and render the template."""
    items = (
        db.query(BriefingItem)
        .options(joinedload(BriefingItem.company), joinedload(BriefingItem.analysis))
        .filter(BriefingItem.briefing_date == briefing_date)
        .join(Company, BriefingItem.company_id == Company.id)
        .order_by(Company.cto_need_score.desc().nulls_last())
        .all()
    )

    today = date.today()
    prev_date = (briefing_date - timedelta(days=1)).isoformat()
    next_date = (briefing_date + timedelta(days=1)).isoformat() if briefing_date < today else None

    # Check for error flash from query params
    error = request.query_params.get("error")

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
        },
    )

