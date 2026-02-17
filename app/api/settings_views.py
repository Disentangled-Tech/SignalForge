"""Settings page HTML routes."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_ui_auth
from app.models.job_run import JobRun
from app.models.user import User
from app.services.settings_service import (
    get_app_settings,
    get_operator_profile,
    update_app_settings,
    update_operator_profile,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    user: User = Depends(require_ui_auth),
    db: Session = Depends(get_db),
):
    """Render settings page with current values and recent job runs (issue #27)."""
    settings = get_app_settings(db)
    flash_message = request.query_params.get("success")
    error = request.query_params.get("error")

    recent_jobs = (
        db.query(JobRun)
        .order_by(JobRun.started_at.desc())
        .limit(20)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "settings/index.html",
        {
            "settings": settings,
            "user": user,
            "flash_message": flash_message or error,
            "flash_type": "error" if error else "success" if flash_message else None,
            "recent_jobs": recent_jobs,
        },
    )


@router.post("/settings")
def settings_save(
    request: Request,
    user: User = Depends(require_ui_auth),
    db: Session = Depends(get_db),
    briefing_time: str = Form(""),
    briefing_email: str = Form(""),
    scoring_weights: str = Form(""),
):
    """Save settings from form and redirect back."""
    updates: dict[str, str] = {}

    if briefing_time.strip():
        updates["briefing_time"] = briefing_time.strip()

    if briefing_email.strip():
        updates["briefing_email"] = briefing_email.strip()

    # Validate scoring_weights JSON if provided
    scoring_text = scoring_weights.strip()
    if scoring_text:
        try:
            parsed = json.loads(scoring_text)
            if not isinstance(parsed, dict):
                return RedirectResponse(
                    url="/settings?error=Scoring+weights+must+be+a+JSON+object",
                    status_code=303,
                )
            updates["scoring_weights"] = scoring_text
        except json.JSONDecodeError:
            return RedirectResponse(
                url="/settings?error=Invalid+JSON+in+scoring+weights",
                status_code=303,
            )

    update_app_settings(db, updates)
    return RedirectResponse(url="/settings?success=Settings+saved", status_code=303)


@router.get("/settings/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    user: User = Depends(require_ui_auth),
    db: Session = Depends(get_db),
):
    """Render operator profile editor."""
    content = get_operator_profile(db)
    flash_message = request.query_params.get("success")
    return templates.TemplateResponse(
        request,
        "settings/profile.html",
        {
            "profile_content": content,
            "user": user,
            "flash_message": flash_message,
            "flash_type": "success" if flash_message else None,
        },
    )


@router.post("/settings/profile")
def profile_save(
    request: Request,
    user: User = Depends(require_ui_auth),
    db: Session = Depends(get_db),
    content: str = Form(""),
):
    """Save operator profile and redirect back."""
    update_operator_profile(db, content)
    return RedirectResponse(
        url="/settings/profile?success=Profile+saved", status_code=303
    )

