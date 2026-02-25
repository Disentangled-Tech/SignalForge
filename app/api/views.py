"""HTML-serving view routes for the SignalForge UI."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import AUTH_COOKIE, get_current_user, get_db, validate_uuid_param_or_422
from app.config import get_settings
from app.db.session import SessionLocal
from app.models.analysis_record import AnalysisRecord
from app.models.briefing_item import BriefingItem
from app.models.job_run import JobRun
from app.models.signal_record import SignalRecord
from app.models.user import User
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.schemas.company import CompanyCreate, CompanySource, CompanyUpdate
from app.services.analysis import ALLOWED_STAGES
from app.services.auth import authenticate_user, create_access_token
from app.services.company import (
    bulk_import_companies,
    create_company,
    delete_company,
    get_company,
    list_companies,
    update_company,
)
from app.services.outreach_history import (
    OutreachCooldownBlockedError,
    create_outreach_record,
    delete_outreach_record,
    get_draft_for_company,
    list_outreach_for_company,
    update_outreach_outcome,
)
from app.services.pack_resolver import get_default_pack_id, get_pack_for_workspace
from app.services.scoring import get_display_scores_for_companies, get_display_scores_with_bands

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


def _resolve_workspace_id(request: Request) -> str | None:
    """Resolve workspace_id from request when multi_workspace_enabled.

    Returns workspace_id from query_params or request.state, or None when
    multi_workspace is disabled or no workspace in request (use default).
    """
    if not get_settings().multi_workspace_enabled:
        return None
    ws = request.query_params.get("workspace_id") or getattr(
        request.state, "workspace_id", None
    )
    if ws is not None:
        validate_uuid_param_or_422(ws, "workspace_id")
    return ws


def _require_workspace_access(
    db: Session, user: User, workspace_id: str | None
) -> None:
    """Raise 403 if user does not have access to workspace (Phase 3).

    Only enforced when multi_workspace_enabled and workspace_id is not None.
    Default workspace allowed for all (backfilled on migration).
    """
    if not get_settings().multi_workspace_enabled or workspace_id is None:
        return
    from app.services.workspace_access import user_has_access_to_workspace

    if not user_has_access_to_workspace(db, user, workspace_id):
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this workspace",
        )


# ── Public routes ────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
def index():
    """Redirect root to companies list."""
    return RedirectResponse(url="/companies", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Render login form."""
    return templates.TemplateResponse(request, "login.html", {"request": request})


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
            request,
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

_VALID_SORT_BY = frozenset({"score", "name", "last_scan_at", "created_at"})
_VALID_SORT_ORDER = frozenset({"asc", "desc"})
_DEFAULT_ORDER: dict[str, str] = {
    "score": "desc",
    "name": "asc",
    "last_scan_at": "desc",
    "created_at": "desc",
}
_PAGE_SIZE = 25


@router.get("/companies", response_class=HTMLResponse)
def companies_list(
    request: Request,
    search: str | None = None,
    sort_by: str | None = None,
    order: str | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
):
    """Render companies list page."""
    sort_by = sort_by if sort_by in _VALID_SORT_BY else "score"
    sort_order = order if order in _VALID_SORT_ORDER else _DEFAULT_ORDER[sort_by]
    page = max(1, page)
    # Phase 3: scope display scores by workspace when multi_workspace enabled
    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID
    _require_workspace_access(db, user, workspace_id)
    companies, total = list_companies(
        db,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search,
        page=page,
        page_size=_PAGE_SIZE,
        workspace_id=workspace_id,
    )
    company_ids = [c.id for c in companies]
    company_scores, company_bands = get_display_scores_with_bands(
        db, company_ids, workspace_id=workspace_id
    )
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE) if total else 1

    # Check if a full scan is already running (for Scan all button state)
    # Scope by workspace_id for multi-tenant readiness; include legacy jobs (workspace_id=None)
    _default_ws = UUID(DEFAULT_WORKSPACE_ID)
    scan_all_running = (
        db.query(JobRun)
        .filter(
            JobRun.job_type == "scan",
            JobRun.status == "running",
            or_(
                JobRun.workspace_id == _default_ws,
                JobRun.workspace_id.is_(None),
            ),
        )
        .first()
        is not None
    )
    scan_all_param = request.query_params.get("scan_all")
    if scan_all_param == "queued":
        flash_message = "Scan all queued. Check Settings for progress."
        flash_type = "success"
    elif scan_all_param == "running":
        flash_message = "A scan is already running. Check Settings for progress."
        flash_type = "error"
    else:
        flash_message = request.query_params.get("success")
        flash_type = "success" if flash_message else None

    return templates.TemplateResponse(
        request,
        "companies/list.html",
        {
            "request": request,
            "user": user,
            "companies": companies,
            "company_scores": company_scores,
            "company_bands": company_bands,
            "search": search,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "total": total,
            "page": page,
            "page_size": _PAGE_SIZE,
            "total_pages": total_pages,
            "flash_message": flash_message,
            "flash_type": flash_type if flash_message else None,
            "scan_all_running": scan_all_running,
            "workspace_id": workspace_id if get_settings().multi_workspace_enabled else None,
        },
    )


# ── Companies: add ───────────────────────────────────────────────────

_URL_PATTERN = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


def _is_valid_url(s: str) -> bool:
    """Return True if s is empty or a valid http(s) URL."""
    s = s.strip()
    if not s:
        return True
    return bool(_URL_PATTERN.match(s))


@router.get("/companies/add", response_class=HTMLResponse)
def companies_add_form(
    request: Request,
    user: User = Depends(_require_ui_auth),
):
    """Render add company form."""
    return templates.TemplateResponse(
        request,
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

    # Validate URL fields when non-empty
    if website_url.strip() and not _is_valid_url(website_url):
        errors.append("Website URL must be a valid URL (e.g. https://example.com).")
    if founder_linkedin_url.strip() and not _is_valid_url(founder_linkedin_url):
        errors.append("Founder LinkedIn URL must be a valid URL.")
    if company_linkedin_url.strip() and not _is_valid_url(company_linkedin_url):
        errors.append("Company LinkedIn URL must be a valid URL.")

    if errors:
        return templates.TemplateResponse(
            request,
            "companies/add.html",
            {"request": request, "user": user, "form_data": form_data, "errors": errors},
            status_code=422,
        )

    try:
        source_enum = CompanySource(source) if source else CompanySource.manual
    except ValueError:
        source_enum = CompanySource.manual

    try:
        data = CompanyCreate(
            company_name=company_name.strip(),
            website_url=website_url.strip() or None,
            founder_name=founder_name.strip() or None,
            founder_linkedin_url=founder_linkedin_url.strip() or None,
            company_linkedin_url=company_linkedin_url.strip() or None,
            notes=notes.strip() or None,
            source=source_enum,
        )
    except ValidationError as e:
        for err in e.errors():
            msg = err.get("msg", "Invalid value")
            loc = err.get("loc", ())
            field = loc[0] if loc else "field"
            errors.append(f"{field}: {msg}")
        return templates.TemplateResponse(
            request,
            "companies/add.html",
            {"request": request, "user": user, "form_data": form_data, "errors": errors},
            status_code=422,
        )

    result = create_company(db, data)
    return RedirectResponse(url=f"/companies/{result.id}", status_code=302)


# ── Companies: import ────────────────────────────────────────────────


@router.get("/companies/import", response_class=HTMLResponse)
def companies_import_form(
    request: Request,
    user: User = Depends(_require_ui_auth),
):
    """Render bulk import form."""
    return templates.TemplateResponse(
        request,
        "companies/import.html",
        {"request": request, "user": user},
    )


@router.post("/companies/import", response_class=HTMLResponse)
def companies_import_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
    csv_file: UploadFile | None = File(None),
    json_data: str = Form(""),
):
    """Handle bulk import form submission (CSV file or JSON paste)."""
    companies: list[CompanyCreate] = []
    errors: list[str] = []

    if csv_file is not None and csv_file.filename:
        # Parse CSV upload
        try:
            content = csv_file.file.read().decode("utf-8")
            reader = csv.DictReader(io.StringIO(content))
            for _idx, row in enumerate(reader, start=1):
                name = (row.get("company_name") or "").strip()
                if not name:
                    continue
                companies.append(
                    CompanyCreate(
                        company_name=name,
                        website_url=row.get("website_url") or None,
                        founder_name=row.get("founder_name") or None,
                        founder_linkedin_url=row.get("founder_linkedin_url") or None,
                        company_linkedin_url=row.get("company_linkedin_url") or None,
                        notes=row.get("notes") or None,
                    )
                )
        except Exception as exc:
            errors.append(f"Failed to parse CSV: {exc}")
    elif json_data.strip():
        # Parse JSON paste
        try:
            parsed = json.loads(json_data)
            if not isinstance(parsed, list):
                errors.append("JSON must be an array of objects.")
            else:
                for item in parsed:
                    companies.append(CompanyCreate(**item))
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON: {exc}")
        except Exception as exc:
            errors.append(f"Failed to parse JSON data: {exc}")
    else:
        errors.append("Please upload a CSV file or paste JSON data.")

    if errors:
        return templates.TemplateResponse(
            request,
            "companies/import.html",
            {"request": request, "user": user, "errors": errors},
            status_code=422,
        )

    result = bulk_import_companies(db, companies)
    return templates.TemplateResponse(
        request,
        "companies/import.html",
        {"request": request, "user": user, "result": result},
    )


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

    # Resolve workspace when multi_workspace_enabled (Phase 3)
    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID
    _require_workspace_access(db, user, workspace_id)

    # Latest company scan job (for status display)
    scan_job = (
        db.query(JobRun)
        .filter(
            JobRun.company_id == company_id,
            JobRun.job_type == "company_scan",
        )
        .order_by(JobRun.started_at.desc())
        .first()
    )

    # Latest signals (most recent first, limit 20)
    signals = (
        db.query(SignalRecord)
        .filter(SignalRecord.company_id == company_id)
        .order_by(SignalRecord.created_at.desc())
        .limit(20)
        .all()
    )

    # Latest analysis (Phase 3: pack-scoped when multi_workspace)
    from app.services.pack_resolver import (
        get_default_pack_id,
        get_pack_for_workspace,
        resolve_pack,
    )

    pack_id = get_pack_for_workspace(db, workspace_id) or get_default_pack_id(db)
    default_pack_id = get_default_pack_id(db)
    analysis_q = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.company_id == company_id)
        .order_by(AnalysisRecord.created_at.desc())
    )
    if pack_id is not None and default_pack_id is not None:
        analysis_q = analysis_q.filter(
            or_(
                AnalysisRecord.pack_id == pack_id,
                (AnalysisRecord.pack_id.is_(None)) & (pack_id == default_pack_id),
            )
        )
    analysis = analysis_q.first()

    # Latest briefing item with outreach (Phase 3: workspace-scoped when multi_workspace)
    from uuid import UUID

    briefing_q = (
        db.query(BriefingItem)
        .filter(BriefingItem.company_id == company_id)
        .order_by(BriefingItem.created_at.desc())
    )
    if workspace_id is not None:
        ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
        default_uuid = UUID(DEFAULT_WORKSPACE_ID)
        if ws_uuid == default_uuid:
            briefing_q = briefing_q.filter(
                (BriefingItem.workspace_id == ws_uuid)
                | (BriefingItem.workspace_id.is_(None))
            )
        else:
            briefing_q = briefing_q.filter(BriefingItem.workspace_id == ws_uuid)
    briefing = briefing_q.first()

    # Outreach history and draft for pre-fill (Phase 3: scope by workspace)
    outreach_history = list_outreach_for_company(
        db, company_id, workspace_id=workspace_id
    )
    draft_message = get_draft_for_company(
        db, company_id, workspace_id=workspace_id
    )

    # Repair: if analysis exists and stored score differs from recomputed, persist correct value.
    # Only run when using the default pack: cto_need_score caches default-pack score only.
    if analysis is not None and pack_id is not None and default_pack_id is not None and pack_id == default_pack_id:
        from app.services.scoring import calculate_score, get_custom_weights, score_company

        custom_weights = get_custom_weights(db)
        pack = resolve_pack(db, pack_id) if pack_id else None
        pain_signals = (
            analysis.pain_signals_json if isinstance(analysis.pain_signals_json, dict) else {}
        )
        recomputed_score = calculate_score(
            pain_signals=pain_signals,
            stage=analysis.stage or "",
            custom_weights=custom_weights,
            pack=pack,
            db=db,
        )
        if company.cto_need_score != recomputed_score:
            score_company(db, company_id, analysis, pack=pack, pack_id=pack_id)
            company = get_company(db, company_id) or company

    # Display score and band: pack-scoped (ReadinessSnapshot > cto_need_score)
    from app.services.score_resolver import get_company_score_with_band

    recomputed_score, recommendation_band = get_company_score_with_band(
        db, company_id, workspace_id=workspace_id
    )

    # Query param for one-time flash: ?rescan=queued | ?rescan=running
    rescan_param = request.query_params.get("rescan")
    # Success flash from edit (issue #50)
    success = request.query_params.get("success")
    # Outreach form validation error
    outreach_error = request.query_params.get("outreach_error")
    # Default for datetime-local input (current time in local format)
    now_for_datetime_local = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")

    return templates.TemplateResponse(
        request,
        "companies/detail.html",
        {
            "request": request,
            "user": user,
            "company": company,
            "signals": signals,
            "analysis": analysis,
            "briefing": briefing,
            "outreach_history": outreach_history,
            "draft_message": draft_message,
            "recomputed_score": recomputed_score,
            "recommendation_band": recommendation_band,
            "scan_job": scan_job,
            "rescan_param": rescan_param,
            "flash_message": success,
            "flash_type": "success" if success else None,
            "outreach_error": outreach_error,
            "now_for_datetime_local": now_for_datetime_local,
            "workspace_id": workspace_id if get_settings().multi_workspace_enabled else None,
        },
    )


# ── Companies: outreach ──────────────────────────────────────────────

_OUTREACH_TYPES = frozenset({"email", "linkedin_dm", "warm_intro", "other"})
_OUTREACH_OUTCOMES = frozenset({"replied", "declined", "no_response", "other"})


def _company_redirect_url(company_id: int, params: dict[str, str] | None = None) -> str:
    """Build redirect URL for company detail, optionally with query params."""
    base = f"/companies/{company_id}"
    if not params:
        return base
    qs = "&".join(f"{k}={quote(v)}" for k, v in params.items() if v)
    return f"{base}?{qs}" if qs else base


@router.post("/companies/{company_id}/outreach")
def company_outreach_add(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
    sent_at: str = Form(""),
    outreach_type: str = Form(""),
    message: str = Form(""),
    notes: str = Form(""),
    outcome: str = Form(""),
):
    """Add an outreach record for a company."""
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    # Phase 3: scope by workspace; default to default workspace when missing (prevents cross-tenant)
    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID
    _require_workspace_access(db, user, workspace_id)

    errors: list[str] = []
    if not sent_at.strip():
        errors.append("Sent date/time is required.")
    if not outreach_type.strip():
        errors.append("Outreach type is required.")
    elif outreach_type.strip() not in _OUTREACH_TYPES:
        errors.append(f"Outreach type must be one of: {', '.join(sorted(_OUTREACH_TYPES))}")
    outcome_val = outcome.strip() or None
    if outcome_val is not None and outcome_val not in _OUTREACH_OUTCOMES:
        errors.append(f"Outcome must be one of: {', '.join(sorted(_OUTREACH_OUTCOMES))}")

    if errors:
        params = {"outreach_error": errors[0]}
        if workspace_id:
            params["workspace_id"] = workspace_id
        return RedirectResponse(
            url=_company_redirect_url(company_id, params),
            status_code=303,
        )

    # Parse sent_at (datetime-local format: YYYY-MM-DDTHH:MM)
    try:
        sent_dt = datetime.fromisoformat(sent_at.strip().replace("Z", "+00:00"))
        if sent_dt.tzinfo is None:
            sent_dt = sent_dt.replace(tzinfo=UTC)
    except ValueError:
        params = {"outreach_error": "Invalid date time format"}
        if workspace_id:
            params["workspace_id"] = workspace_id
        return RedirectResponse(
            url=_company_redirect_url(company_id, params),
            status_code=303,
        )

    try:
        create_outreach_record(
            db,
            company_id=company_id,
            sent_at=sent_dt,
            outreach_type=outreach_type.strip(),
            message=message.strip() or None,
            notes=notes.strip() or None,
            outcome=outcome_val,
            workspace_id=workspace_id,
        )
    except OutreachCooldownBlockedError as e:
        params = {"outreach_error": e.reason}
        if workspace_id:
            params["workspace_id"] = workspace_id
        return RedirectResponse(
            url=_company_redirect_url(company_id, params),
            status_code=303,
        )
    params = {"success": "Outreach recorded"}
    if workspace_id:
        params["workspace_id"] = workspace_id
    return RedirectResponse(
        url=_company_redirect_url(company_id, params),
        status_code=303,
    )


@router.post("/companies/{company_id}/outreach/{outreach_id}/edit")
def company_outreach_edit(
    request: Request,
    company_id: int,
    outreach_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
    outcome: str = Form(""),
):
    """Update the outcome of an outreach record."""
    # Phase 3: default to default workspace when missing (prevents cross-tenant modify)
    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID
    _require_workspace_access(db, user, workspace_id)

    outcome_val = outcome.strip() or None
    if outcome_val is not None and outcome_val not in _OUTREACH_OUTCOMES:
        params = {"outreach_error": "Invalid outcome"}
        if workspace_id:
            params["workspace_id"] = workspace_id
        return RedirectResponse(
            url=_company_redirect_url(company_id, params),
            status_code=303,
        )
    updated = update_outreach_outcome(
        db,
        company_id=company_id,
        outreach_id=outreach_id,
        outcome=outcome_val,
        workspace_id=workspace_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Outreach record not found")
    params = {"success": "Outcome updated"}
    if workspace_id:
        params["workspace_id"] = workspace_id
    return RedirectResponse(
        url=_company_redirect_url(company_id, params),
        status_code=303,
    )


@router.post("/companies/{company_id}/outreach/{outreach_id}/delete")
def company_outreach_delete(
    request: Request,
    company_id: int,
    outreach_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
):
    """Delete an outreach record."""
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    # Phase 3: default to default workspace when missing (prevents cross-tenant delete)
    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID
    _require_workspace_access(db, user, workspace_id)

    deleted = delete_outreach_record(
        db, company_id, outreach_id, workspace_id=workspace_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Outreach record not found")

    params = {"success": "Outreach deleted"}
    if workspace_id:
        params["workspace_id"] = workspace_id
    return RedirectResponse(
        url=_company_redirect_url(company_id, params),
        status_code=303,
    )


# ── Companies: edit (issue #50) ──────────────────────────────────────


@router.get("/companies/{company_id}/edit", response_class=HTMLResponse)
def company_edit_form(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
):
    """Render edit company form with pre-filled data."""
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    # Map CompanyRead to form_data (same keys as add form)
    form_data = {
        "company_name": company.company_name,
        "website_url": company.website_url or "",
        "founder_name": company.founder_name or "",
        "founder_linkedin_url": company.founder_linkedin_url or "",
        "company_linkedin_url": company.company_linkedin_url or "",
        "notes": company.notes or "",
        "source": company.source.value if company.source else "manual",
        "target_profile_match": "on" if company.target_profile_match else "",
        "current_stage": company.current_stage or "",
    }
    return templates.TemplateResponse(
        request,
        "companies/edit.html",
        {
            "request": request,
            "user": user,
            "company": company,
            "form_data": form_data,
            "errors": [],
            "allowed_stages": sorted(ALLOWED_STAGES),
        },
    )


@router.post("/companies/{company_id}/edit", response_class=HTMLResponse)
def company_edit_submit(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
    company_name: str = Form(""),
    website_url: str = Form(""),
    founder_name: str = Form(""),
    founder_linkedin_url: str = Form(""),
    company_linkedin_url: str = Form(""),
    notes: str = Form(""),
    source: str = Form("manual"),
    target_profile_match: str = Form(""),
    current_stage: str = Form(""),
):
    """Handle edit company form submission."""
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    form_data = {
        "company_name": company_name,
        "website_url": website_url,
        "founder_name": founder_name,
        "founder_linkedin_url": founder_linkedin_url,
        "company_linkedin_url": company_linkedin_url,
        "notes": notes,
        "source": source,
        "target_profile_match": target_profile_match,
        "current_stage": current_stage,
    }

    errors: list[str] = []
    if not company_name.strip():
        errors.append("Company name is required.")

    if website_url.strip() and not _is_valid_url(website_url):
        errors.append("Website URL must be a valid URL (e.g. https://example.com).")
    if founder_linkedin_url.strip() and not _is_valid_url(founder_linkedin_url):
        errors.append("Founder LinkedIn URL must be a valid URL.")
    if company_linkedin_url.strip() and not _is_valid_url(company_linkedin_url):
        errors.append("Company LinkedIn URL must be a valid URL.")

    if errors:
        return templates.TemplateResponse(
            request,
            "companies/edit.html",
            {
                "request": request,
                "user": user,
                "company": company,
                "form_data": form_data,
                "errors": errors,
                "allowed_stages": sorted(ALLOWED_STAGES),
            },
            status_code=422,
        )

    try:
        source_enum = CompanySource(source) if source else CompanySource.manual
    except ValueError:
        source_enum = CompanySource.manual

    data = CompanyUpdate(
        company_name=company_name.strip(),
        website_url=website_url.strip() or None,
        founder_name=founder_name.strip() or None,
        founder_linkedin_url=founder_linkedin_url.strip() or None,
        company_linkedin_url=company_linkedin_url.strip() or None,
        notes=notes.strip() or None,
        source=source_enum,
        target_profile_match="on" if target_profile_match == "on" else None,
        current_stage=current_stage.strip() or None,
    )
    result = update_company(db, company_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return RedirectResponse(url=f"/companies/{company_id}?success=Company+updated", status_code=303)


# ── Companies: scan all ──────────────────────────────────────────────


def _run_scan_all_background(workspace_id: str | None = None) -> None:
    """Background task: run full scan across all companies. Uses its own DB session."""
    from app.services.scan_orchestrator import run_scan_all

    db = SessionLocal()
    try:
        asyncio.run(run_scan_all(db, workspace_id=workspace_id))
    finally:
        db.close()


@router.post("/companies/scan-all")
async def companies_scan_all(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
):
    """Queue a full scan across all companies, then redirect back to companies list."""
    # Phase 3: resolve workspace, enforce access when multi_workspace enabled
    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID
    _require_workspace_access(db, user, workspace_id)

    ws_uuid = UUID(str(workspace_id)) if workspace_id else UUID(DEFAULT_WORKSPACE_ID)
    running_job = (
        db.query(JobRun)
        .filter(
            JobRun.job_type == "scan",
            JobRun.status == "running",
            or_(
                JobRun.workspace_id == ws_uuid,
                JobRun.workspace_id.is_(None),
            ),
        )
        .first()
    )
    if running_job is not None:
        url = "/companies?scan_all=running"
        if workspace_id:
            url += f"&workspace_id={workspace_id}"
        return RedirectResponse(url=url, status_code=303)

    background_tasks.add_task(_run_scan_all_background, workspace_id)
    url = "/companies?scan_all=queued"
    if workspace_id:
        url += f"&workspace_id={workspace_id}"
    return RedirectResponse(url=url, status_code=303)


# ── Companies: rescan ────────────────────────────────────────────────


def _run_rescan_background(company_id: int, job_id: int) -> None:
    """Background task: run scan pipeline and update JobRun. Uses its own DB session."""
    from app.services.scan_orchestrator import run_scan_company_with_job

    db = SessionLocal()
    try:
        asyncio.run(run_scan_company_with_job(db, company_id, job_id=job_id))
    finally:
        db.close()


@router.post("/companies/{company_id}/rescan")
async def company_rescan(
    request: Request,
    company_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(_require_ui_auth),
):
    """Queue scan + analysis + scoring for a company, then redirect back."""
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    # Phase 3: resolve workspace, enforce access, use workspace's pack
    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID
    _require_workspace_access(db, user, workspace_id)

    ws_uuid = UUID(str(workspace_id)) if workspace_id else UUID(DEFAULT_WORKSPACE_ID)
    pack_id = get_pack_for_workspace(db, workspace_id) or get_default_pack_id(db)

    # Check if a scan is already running for this company (same workspace or legacy)
    running_job = (
        db.query(JobRun)
        .filter(
            JobRun.company_id == company_id,
            JobRun.job_type == "company_scan",
            JobRun.status == "running",
            or_(
                JobRun.workspace_id == ws_uuid,
                JobRun.workspace_id.is_(None),
            ),
        )
        .order_by(JobRun.started_at.desc())
        .first()
    )
    if running_job is not None:
        params = {"rescan": "running"}
        if workspace_id:
            params["workspace_id"] = workspace_id
        return RedirectResponse(
            url=_company_redirect_url(company_id, params), status_code=302
        )

    # Create JobRun and queue background task (pack_id, workspace_id for audit)
    job = JobRun(
        job_type="company_scan",
        company_id=company_id,
        status="running",
        pack_id=pack_id,
        workspace_id=ws_uuid,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_rescan_background, company_id, job.id)

    params = {"rescan": "queued"}
    if workspace_id:
        params["workspace_id"] = workspace_id
    return RedirectResponse(
        url=_company_redirect_url(company_id, params), status_code=302
    )


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
