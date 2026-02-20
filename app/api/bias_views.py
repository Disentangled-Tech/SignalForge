"""Bias report UI routes (Issue #112)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_ui_auth
from app.models.bias_report import BiasReport
from app.models.user import User
from app.services.bias_audit import run_bias_audit

router = APIRouter()

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/bias-reports", response_class=HTMLResponse)
def bias_reports_list(
    request: Request,
    user: User = Depends(require_ui_auth),
    db: Session = Depends(get_db),
):
    """List bias reports (newest first)."""
    reports = (
        db.query(BiasReport)
        .order_by(BiasReport.report_month.desc())
        .limit(50)
        .all()
    )
    flash_message = request.query_params.get("success")
    error = request.query_params.get("error")

    return templates.TemplateResponse(
        request,
        "bias/list.html",
        {
            "user": user,
            "reports": reports,
            "flash_message": flash_message or error,
            "flash_type": "error" if error else "success" if flash_message else None,
        },
    )


@router.get("/bias-reports/{report_id}", response_class=HTMLResponse)
def bias_report_detail(
    request: Request,
    report_id: int,
    user: User = Depends(require_ui_auth),
    db: Session = Depends(get_db),
):
    """Show full bias report detail."""
    report = db.query(BiasReport).filter(BiasReport.id == report_id).first()
    if report is None:
        return RedirectResponse(url="/bias-reports?error=Report+not+found", status_code=302)

    payload = report.payload or {}
    return templates.TemplateResponse(
        request,
        "bias/detail.html",
        {
            "user": user,
            "report": report,
            "payload": payload,
        },
    )


@router.post("/bias-reports/run")
def bias_reports_run(
    user: User = Depends(require_ui_auth),
    db: Session = Depends(get_db),
):
    """Trigger bias audit (run_bias_audit). Redirects to list with success/error."""
    try:
        result = run_bias_audit(db, report_month=None)
        if result["status"] == "completed":
            return RedirectResponse(
                url=f"/bias-reports?success=Report+generated+for+{result['surfaced_count']}+companies",
                status_code=303,
            )
        return RedirectResponse(
            url=f"/bias-reports?error={result.get('error', 'Audit failed')}",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(
            url=f"/bias-reports?error={str(exc)[:100]}",
            status_code=303,
        )
