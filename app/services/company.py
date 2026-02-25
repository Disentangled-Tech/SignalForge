"""Company CRUD service with field mapping between schema and model."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.company import Company
from app.schemas.company import (
    BulkImportResponse,
    BulkImportRow,
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
)
from app.services.company_resolver import resolve_or_create_company
from app.services.scoring import get_display_scores_for_companies

# ── Field mapping helpers ────────────────────────────────────────────


def _schema_to_model_data(data: CompanyCreate | CompanyUpdate, *, is_update: bool = False) -> dict:
    """Map Pydantic schema fields to SQLAlchemy model column names.

    - company_name -> name
    - target_profile_match (str|None) -> bool
    """
    raw = data.model_dump(exclude_unset=is_update)
    mapped: dict = {}
    for key, value in raw.items():
        if key == "company_name":
            mapped["name"] = value
        elif key == "target_profile_match":
            # str|None -> bool: truthy string = True, None/empty = False
            mapped["target_profile_match"] = bool(value)
        elif key == "source":
            # CompanySource enum -> its string value
            mapped["source"] = value.value if hasattr(value, "value") else value
        else:
            mapped[key] = value
    return mapped


def _model_to_read(company: Company) -> CompanyRead:
    """Map a Company ORM instance to a CompanyRead schema.

    - name -> company_name
    - target_profile_match (bool) -> str|None
    """
    return CompanyRead(
        id=company.id,
        company_name=company.name,
        domain=company.domain,
        website_url=company.website_url,
        founder_name=company.founder_name,
        founder_linkedin_url=company.founder_linkedin_url,
        company_linkedin_url=company.company_linkedin_url,
        notes=company.notes,
        source=company.source,
        target_profile_match=str(company.target_profile_match) if company.target_profile_match else None,
        cto_need_score=company.cto_need_score,
        current_stage=company.current_stage,
        created_at=company.created_at,
        updated_at=company.updated_at,
        last_scan_at=company.last_scan_at,
    )


# ── Sort helpers ─────────────────────────────────────────────────────

def _order_clause(column, ascending: bool):
    """Return SQLAlchemy order clause for column (asc or desc)."""
    return column.asc() if ascending else column.desc()


# ── CRUD operations ─────────────────────────────────────────────────


def list_companies(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    search: str | None = None,
    workspace_id: str | None = None,
) -> tuple[list[CompanyRead], int]:
    """Return paginated list of companies with optional search and sort.

    When sort_by='score', sorts by display score (recomputed from latest analysis)
    so the order matches what users see. Other sorts use stored DB columns.
    sort_order: 'asc' or 'desc'.
    When workspace_id provided (Phase 3), display scores use workspace's active pack.
    """
    ascending = sort_order == "asc"
    base_query = db.query(Company)
    if search:
        pattern = f"%{search}%"
        base_query = base_query.filter(
            or_(
                Company.name.ilike(pattern),
                Company.founder_name.ilike(pattern),
                Company.notes.ilike(pattern),
            )
        )

    total = base_query.count()

    if sort_by == "score":
        # Sort by display score (from analysis) so order matches what users see
        company_ids = [row[0] for row in base_query.with_entities(Company.id).all()]
        display_scores = get_display_scores_for_companies(
            db, company_ids, workspace_id=workspace_id
        )
        # Companies without score use -1; reverse for asc (low first)
        mult = 1 if ascending else -1
        sorted_ids = sorted(
            company_ids,
            key=lambda cid: (mult * (display_scores.get(cid) or -1), cid),
        )
        start = (page - 1) * page_size
        page_ids = sorted_ids[start : start + page_size]
        if not page_ids:
            return [], total
        # Fetch companies in page order (preserve sort)
        id_to_company = {
            c.id: c
            for c in db.query(Company).filter(Company.id.in_(page_ids)).all()
        }
        companies = [id_to_company[cid] for cid in page_ids if cid in id_to_company]
    else:
        column_map = {
            "name": Company.name,
            "last_scan_at": Company.last_scan_at,
            "created_at": Company.created_at,
        }
        col = column_map.get(sort_by, Company.created_at)
        base_query = base_query.order_by(_order_clause(col, ascending))
        offset = (page - 1) * page_size
        companies = base_query.offset(offset).limit(page_size).all()

    return [_model_to_read(c) for c in companies], total


def get_company(db: Session, company_id: int) -> CompanyRead | None:
    """Return a single company by ID, or None if not found."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        return None
    return _model_to_read(company)


def create_company(db: Session, data: CompanyCreate) -> CompanyRead:
    """Create a new company from validated schema data."""
    model_data = _schema_to_model_data(data)
    company = Company(**model_data)
    db.add(company)
    db.commit()
    db.refresh(company)
    return _model_to_read(company)


def update_company(
    db: Session, company_id: int, data: CompanyUpdate
) -> CompanyRead | None:
    """Update an existing company. Returns None if not found."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        return None

    model_data = _schema_to_model_data(data, is_update=True)
    for key, value in model_data.items():
        setattr(company, key, value)

    db.commit()
    db.refresh(company)
    return _model_to_read(company)


def delete_company(db: Session, company_id: int) -> bool:
    """Delete a company by ID. Returns True if deleted, False if not found."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        return False
    db.delete(company)
    db.commit()
    return True



# ── Bulk import ──────────────────────────────────────────────────────


def bulk_import_companies(
    db: Session, companies: list[CompanyCreate]
) -> BulkImportResponse:
    """Import multiple companies, skipping duplicates.

    Returns a summary with per-row details.
    """
    rows: list[BulkImportRow] = []
    created = 0
    duplicates = 0
    errors = 0

    for idx, data in enumerate(companies, start=1):
        name = data.company_name.strip()
        if not name:
            rows.append(
                BulkImportRow(
                    row=idx,
                    company_name=name or "(empty)",
                    status="error",
                    detail="Missing company_name",
                )
            )
            errors += 1
            continue

        # Duplicate detection: use resolver (domain, LinkedIn, normalized name)
        try:
            company, was_created = resolve_or_create_company(db, data)
            if not was_created:
                rows.append(
                    BulkImportRow(
                        row=idx,
                        company_name=name,
                        status="duplicate",
                        detail=f"Company '{name}' already exists (id={company.id})",
                    )
                )
                duplicates += 1
                continue
            rows.append(
                BulkImportRow(
                    row=idx,
                    company_name=name,
                    status="created",
                )
            )
            created += 1
        except Exception as exc:
            rows.append(
                BulkImportRow(
                    row=idx,
                    company_name=name,
                    status="error",
                    detail=str(exc),
                )
            )
            errors += 1

    return BulkImportResponse(
        total=len(companies),
        created=created,
        duplicates=duplicates,
        errors=errors,
        rows=rows,
    )