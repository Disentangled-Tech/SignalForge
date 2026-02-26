"""Company CRUD API routes."""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_auth, validate_uuid_param_or_422
from app.api.views import _require_workspace_access
from app.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.company import (
    BulkImportResponse,
    CompanyCreate,
    CompanyList,
    CompanyRead,
    CompanyUpdate,
)
from app.schemas.ranked_companies import RankedCompaniesResponse
from app.services.company import (
    bulk_import_companies,
    delete_company,
    get_company,
    list_companies,
    update_company,
)
from app.services.company_resolver import resolve_or_create_company
from app.services.ranked_companies import get_ranked_companies_for_api

router = APIRouter()


# ── Routes ───────────────────────────────────────────────────────────


@router.get(
    "/top",
    response_model=RankedCompaniesResponse,
    summary="Get top ranked companies",
    description="""Get ranked companies for Daily Briefing UI (Issue #247).

Returns companies ordered by composite/outreach score descending, with
recommendation_band (IGNORE | WATCH | HIGH_PRIORITY), top_signals, and
optional dimension breakdown (momentum, complexity, pressure, leadership_gap).

**Auth**: Required (Bearer token or session cookie).

**Workspace scoping**: When multi_workspace_enabled, pass workspace_id to scope
results. Invalid workspace_id returns 422. Users must have access to the workspace
(403 if not).

**Empty DB**: Returns ``{"companies": [], "total": 0}``.
""",
)
def api_companies_top(
    since: date | None = Query(
        None,
        description="Snapshot date (YYYY-MM-DD). Default: today.",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=100,
        description="Maximum number of companies to return.",
    ),
    workspace_id: str | None = Query(
        None,
        description="Workspace ID (when multi_workspace_enabled). Default workspace if omitted.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
) -> RankedCompaniesResponse:
    """Get top ranked companies for Daily Briefing (Issue #247)."""
    as_of = since if since is not None else date.today()
    settings = get_settings()
    ws_id = workspace_id if settings.multi_workspace_enabled else None
    if ws_id is not None:
        validate_uuid_param_or_422(ws_id, "workspace_id")
        _require_workspace_access(db, user, ws_id)
    companies = get_ranked_companies_for_api(
        db, as_of, limit=limit, workspace_id=ws_id
    )
    return RankedCompaniesResponse(companies=companies, total=len(companies))


@router.get("", response_model=CompanyList)
def api_list_companies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at", pattern="^(score|name|last_scan_at|created_at)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> CompanyList:
    """List companies with pagination, sorting, and optional search."""
    items, total = list_companies(
        db,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=order,
        search=search,
    )
    return CompanyList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{company_id}", response_model=CompanyRead)
def api_get_company(
    company_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> CompanyRead:
    """Get a single company by ID."""
    result = get_company(db, company_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return result


@router.post("", response_model=CompanyRead, status_code=201)
def api_create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> CompanyRead:
    """Create a new company or resolve to existing (idempotent). Returns 201 for both."""
    from app.services.company import _model_to_read

    company, _created = resolve_or_create_company(db, data)
    return _model_to_read(company)


class _BulkImportBody(BaseModel):
    """Request body for JSON bulk import."""

    companies: list[CompanyCreate]


@router.post("/import", response_model=BulkImportResponse)
async def api_import_companies(
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> BulkImportResponse:
    """Bulk import companies from JSON body or CSV file upload.

    - JSON: ``{"companies": [CompanyCreate, ...]}``
    - CSV: multipart file upload with a field named ``file``.
    """
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        # CSV file upload
        form = await request.form()
        file = form.get("file")
        if file is None:
            raise HTTPException(status_code=422, detail="No file field in upload.")
        try:
            content = (await file.read()).decode("utf-8")
        finally:
            await file.close()
        reader = csv.DictReader(io.StringIO(content))
        companies: list[CompanyCreate] = []
        error_rows: list[tuple[int, str]] = []  # (row_number, detail)
        for idx, row in enumerate(reader, start=1):
            name = (row.get("company_name") or "").strip()
            if not name:
                error_rows.append((idx, "Missing company_name"))
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
        result = bulk_import_companies(db, companies)
        # Merge CSV validation errors into the result
        from app.schemas.company import BulkImportRow

        for row_num, detail in error_rows:
            result.rows.append(
                BulkImportRow(
                    row=row_num,
                    company_name="(empty)",
                    status="error",
                    detail=detail,
                )
            )
            result.errors += 1
            result.total += 1
        # Sort rows by row number for consistent output
        result.rows.sort(key=lambda r: r.row)
        return result

    # Default: JSON body
    raw = await request.json()
    body = _BulkImportBody(**raw)
    return bulk_import_companies(db, body.companies)


@router.put("/{company_id}", response_model=CompanyRead)
def api_update_company(
    company_id: int,
    data: CompanyUpdate,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> CompanyRead:
    """Update an existing company."""
    result = update_company(db, company_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return result


@router.delete("/{company_id}", status_code=204)
def api_delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> None:
    """Delete a company."""
    deleted = delete_company(db, company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Company not found")

