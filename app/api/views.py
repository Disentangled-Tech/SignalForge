"""HTML-serving view routes for the SignalForge UI."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import AUTH_COOKIE, get_current_user, get_db
from app.models.analysis_record import AnalysisRecord
from app.models.briefing_item import BriefingItem
from app.models.company import Company
from app.models.signal_record import SignalRecord
from app.models.user import User
from app.schemas.company import CompanyCreate, CompanySource
from app.services.auth import authenticate_user, create_access_token
from app.services.company import create_company, delete_company, get_company, list_companies

logger = logging.getLogger(__name__)

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── Auth helper ──────────────────────────────────────────────────────

def _require_ui_auth(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> User:
    """Require authentication for UI routes; redirect to login on failure."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
    return user


# ── Public routes ────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def index():
    """Redirect root to companies list."""
    return RedirectResponse(url="/companies", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Render login form."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    username: str = Form(""),
    password: str = Form(""),
):
    """Handle login form submission."""
    user = authenticate_user(db, username, password)
    if user is None:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=401,
        )
    token = create_access_token(data={"sub": user.username})
    resp = RedirectResponse(url="/companies", status_code=302)
    resp.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24,
        path="/",
    )
    return resp


@router.get("/logout")
def logout():
    """Clear auth cookie and redirect to login."""
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(key=AUTH_COOKIE, path="/")
    return resp


# ── Companies: list ──────────────────────────────────────────────────

@router.get("/companies", response_class=HTMLResponse)
def companies_list(
    request: Request,
    search: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
):
    """Render companies list page."""
    companies, total = list_companies(db, sort_by="score", search=search)
    return templates.TemplateResponse(
        "companies/list.html",
        {"request": request, "user": user, "companies": companies, "search": search},
    )


# ── Companies: add ───────────────────────────────────────────────────

@router.get("/companies/add", response_class=HTMLResponse)
def companies_add_form(
    request: Request,
    user: User = Depends(_require_ui_auth),
):
    """Render add company form."""
    return templates.TemplateResponse(
        "companies/add.html",
        {"request": request, "user": user, "form_data": {}, "errors": []},
    )


@router.post("/companies/add", response_class=HTMLResponse)
def companies_add_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
    company_name: str = Form(""),
    website_url: str = Form(""),
    founder_name: str = Form(""),
    founder_linkedin_url: str = Form(""),
    company_linkedin_url: str = Form(""),
    notes: str = Form(""),
    source: str = Form("manual"),
):
    """Handle add company form submission."""
    form_data = {
        "company_name": company_name,
        "website_url": website_url,
        "founder_name": founder_name,
        "founder_linkedin_url": founder_linkedin_url,
        "company_linkedin_url": company_linkedin_url,
        "notes": notes,
        "source": source,
    }

    errors: list[str] = []
    if not company_name.strip():
        errors.append("Company name is required.")

    if errors:
        return templates.TemplateResponse(
            "companies/add.html",
            {"request": request, "user": user, "form_data": form_data, "errors": errors},
            status_code=422,
        )

    try:
        source_enum = CompanySource(source) if source else CompanySource.manual
    except ValueError:
        source_enum = CompanySource.manual

    data = CompanyCreate(
        company_name=company_name.strip(),
        website_url=website_url.strip() or None,
        founder_name=founder_name.strip() or None,
        founder_linkedin_url=founder_linkedin_url.strip() or None,
        company_linkedin_url=company_linkedin_url.strip() or None,
        notes=notes.strip() or None,
        source=source_enum,
    )
    create_company(db, data)
    return RedirectResponse(url="/companies", status_code=302)


# ── Companies: detail ────────────────────────────────────────────────

@router.get("/companies/{company_id}", response_class=HTMLResponse)
def company_detail(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
):
    """Render company detail page."""
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    # Latest signals (most recent first, limit 20)
    signals = (
        db.query(SignalRecord)
        .filter(SignalRecord.company_id == company_id)
        .order_by(SignalRecord.created_at.desc())
        .limit(20)
        .all()
    )

    # Latest analysis
    analysis = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.company_id == company_id)
        .order_by(AnalysisRecord.created_at.desc())
        .first()
    )

    # Latest briefing item with outreach
    briefing = (
        db.query(BriefingItem)
        .filter(BriefingItem.company_id == company_id)
        .order_by(BriefingItem.created_at.desc())
        .first()
    )

    return templates.TemplateResponse(
        "companies/detail.html",
        {
            "request": request,
            "user": user,
            "company": company,
            "signals": signals,
            "analysis": analysis,
            "briefing": briefing,
        },
    )


# ── Companies: rescan ────────────────────────────────────────────────

@router.post("/companies/{company_id}/rescan")
async def company_rescan(
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
):
    """Trigger scan + analysis + scoring for a company, then redirect back."""
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        from app.services.scan_orchestrator import run_scan_company
        await run_scan_company(db, company_id)
    except Exception as exc:
        logger.error("Scan failed for company %s: %s", company_id, exc)

    try:
        from app.services.analysis import analyze_company
        analysis = analyze_company(db, company_id)
        if analysis is not None:
            from app.services.scoring import score_company
            score_company(db, company_id, analysis)
    except Exception as exc:
        logger.error("Analysis/scoring failed for company %s: %s", company_id, exc)

    return RedirectResponse(url=f"/companies/{company_id}", status_code=302)


# ── Companies: delete ────────────────────────────────────────────────

@router.post("/companies/{company_id}/delete")
def company_delete(
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
):
    """Delete a company and redirect to list."""
    deleted = delete_company(db, company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Company not found")
    return RedirectResponse(url="/companies", status_code=302)

