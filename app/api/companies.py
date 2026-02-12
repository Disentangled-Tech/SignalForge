"""Company CRUD API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_auth
from app.db.session import get_db
from app.schemas.company import (
    CompanyCreate,
    CompanyList,
    CompanyRead,
    CompanyUpdate,
)
from app.services.company import (
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
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> CompanyList:
    """List companies with pagination, sorting, and optional search."""
    items, total = list_companies(
        db, page=page, page_size=page_size, sort_by=sort_by, search=search
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

