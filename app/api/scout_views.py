"""Scout UI view routes — session auth, workspace-scoped.

User-facing routes for triggering Scout runs, listing runs, and viewing run detail
(evidence bundles). No internal token; workspace resolution from request.
raw_llm_output is never passed to templates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_ui_auth, validate_uuid_param_or_422
from app.api.views import _require_workspace_access, _resolve_workspace_id
from app.config import get_settings
from app.models.scout_run import ScoutRun
from app.models.user import User
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.services.scout.discovery_scout_service import (
    DEFAULT_PAGE_FETCH_LIMIT,
)
from app.services.scout.discovery_scout_service import (
    run as run_scout,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/scout", response_class=HTMLResponse)
def scout_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_ui_auth),
):
    """List Scout runs for the current workspace.

    Workspace-scoped; no cross-tenant data. No raw_llm_output (list shows metadata only).
    """
    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID
    _require_workspace_access(db, user, workspace_id)
    ws_uuid = UUID(workspace_id) if workspace_id else UUID(DEFAULT_WORKSPACE_ID)

    runs = (
        db.query(ScoutRun)
        .options(joinedload(ScoutRun.bundles))
        .filter(ScoutRun.workspace_id == ws_uuid)
        .order_by(ScoutRun.started_at.desc())
        .all()
    )
    run_items = [
        {
            "run_id": str(r.run_id),
            "started_at": r.started_at,
            "status": r.status,
            "bundles_count": len(r.bundles),
        }
        for r in runs
    ]
    error_message = request.query_params.get("error")
    success_message = request.query_params.get("success")
    if error_message:
        flash_message = error_message
        flash_type = "error"
    elif success_message:
        flash_message = success_message
        flash_type = "success"
    else:
        flash_message = None
        flash_type = None
    return templates.TemplateResponse(
        request,
        "scout/list.html",
        {
            "request": request,
            "user": user,
            "runs": run_items,
            "flash_message": flash_message,
            "flash_type": flash_type,
            "workspace_id": workspace_id if get_settings().multi_workspace_enabled else None,
        },
    )


@router.get("/scout/new", response_class=HTMLResponse)
def scout_run_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_ui_auth),
):
    """Show form to trigger a new Scout run.

    Workspace-scoped when multi_workspace enabled. No raw_llm_output (form only).
    """
    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID
    _require_workspace_access(db, user, workspace_id)
    return templates.TemplateResponse(
        request,
        "scout/run_new.html",
        {
            "request": request,
            "user": user,
            "workspace_id": workspace_id if get_settings().multi_workspace_enabled else None,
            "form_data": {},
        },
    )


@router.get("/scout/runs/{run_id}", response_class=HTMLResponse)
def scout_run_detail(
    request: Request,
    run_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_ui_auth),
):
    """Run detail: show run metadata and bundles (candidate, website, hypothesis, evidence).

    Workspace-scoped; raw_llm_output is never passed to the template. 404 if run does not
    exist or user lacks access to its workspace. When workspace_id query is omitted
    (e.g. redirect from trigger), workspace is resolved from the run."""
    validate_uuid_param_or_422(str(run_id), "run_id")
    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        # Resolve workspace from run so redirect from POST /scout/runs needs no query (avoids open-redirect)
        run_by_id = (
            db.query(ScoutRun)
            .options(joinedload(ScoutRun.bundles))
            .filter(ScoutRun.run_id == run_id)
            .first()
        )
        if run_by_id is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Scout run not found")
        ws_uuid = run_by_id.workspace_id or UUID(DEFAULT_WORKSPACE_ID)
        _require_workspace_access(db, user, str(ws_uuid))
        run = run_by_id
        workspace_id = str(ws_uuid)
    else:
        _require_workspace_access(db, user, workspace_id)
        ws_uuid = UUID(workspace_id) if workspace_id else UUID(DEFAULT_WORKSPACE_ID)
        run = (
            db.query(ScoutRun)
            .options(joinedload(ScoutRun.bundles))
            .filter(ScoutRun.run_id == run_id, ScoutRun.workspace_id == ws_uuid)
            .first()
        )
        if run is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Scout run not found")

    bundles_for_template = [
        {
            "candidate_company_name": b.candidate_company_name,
            "company_website": b.company_website,
            "why_now_hypothesis": b.why_now_hypothesis,
            "evidence": b.evidence if isinstance(b.evidence, list) else [],
        }
        for b in run.bundles
    ]
    return templates.TemplateResponse(
        request,
        "scout/run_detail.html",
        {
            "request": request,
            "user": user,
            "run": {
                "run_id": str(run.run_id),
                "started_at": run.started_at,
                "status": run.status,
                "bundles_count": len(run.bundles),
            },
            "bundles": bundles_for_template,
            "workspace_id": workspace_id if get_settings().multi_workspace_enabled else None,
        },
    )


@router.post("/scout/runs")
def scout_run_trigger(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_ui_auth),
    icp_definition: str = Form(..., min_length=1, max_length=4000),
    exclusion_rules: str | None = Form(None),
    page_fetch_limit: int = Form(DEFAULT_PAGE_FETCH_LIMIT, ge=0, le=100),
):
    """Trigger a Scout run.

    Workspace-scoped: resolve workspace from request and enforce access. Redirects to
    list with success or error flash. No raw_llm_output (persistence is server-side only).
    """
    import asyncio

    workspace_id = _resolve_workspace_id(request)
    if get_settings().multi_workspace_enabled and workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID
    _require_workspace_access(db, user, workspace_id)
    ws_uuid = UUID(workspace_id) if workspace_id else UUID(DEFAULT_WORKSPACE_ID)

    try:
        run_id, _bundles, _metadata = asyncio.run(
            run_scout(
                db,
                icp_definition=icp_definition.strip(),
                exclusion_rules=(exclusion_rules or "").strip() or None,
                page_fetch_limit=page_fetch_limit,
                workspace_id=ws_uuid,
            )
        )
        db.commit()
        # Redirect to list with success message only (no run_id in URL to satisfy open-redirect SAST).
        # run_id is server-generated; user can open the new run from the list.
        return RedirectResponse(
            url="/scout?success=Scout+run+started",
            status_code=303,
        )
    except Exception as exc:
        logger.exception("Scout run failed: %s", exc)
        db.rollback()
        return RedirectResponse(
            url="/scout?error=Scout+run+failed",
            status_code=303,
        )
