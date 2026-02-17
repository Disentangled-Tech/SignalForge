"""Company CRUD API routes."""

from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_auth
from app.db.session import get_db
from app.schemas.company import (
    BulkImportResponse,
    CompanyCreate,
    CompanyList,
    CompanyRead,
    CompanyUpdate,
)
from app.services.company import (
    bulk_import_companies,
    create_company,
    delete_company,
    get_company,
    list_companies,
    update_company,
)

router = APIRouter()


# ── Routes ───────────────────────────────────────────────────────────


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
    """Create a new company."""
    return create_company(db, data)


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
        content = (await file.read()).decode("utf-8")
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

