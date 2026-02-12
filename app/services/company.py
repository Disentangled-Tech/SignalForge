"""Company CRUD service with field mapping between schema and model."""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.company import Company
from app.schemas.company import (
    BulkImportResponse,
    BulkImportRow,
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
)


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

_SORT_MAP = {
    "score": Company.cto_need_score.desc(),
    "name": Company.name.asc(),
    "last_scan_at": Company.last_scan_at.desc(),
    "created_at": Company.created_at.desc(),
}


# ── CRUD operations ─────────────────────────────────────────────────


def list_companies(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    search: str | None = None,
) -> tuple[list[CompanyRead], int]:
    """Return paginated list of companies with optional search and sort."""
    query = db.query(Company)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Company.name.ilike(pattern),
                Company.founder_name.ilike(pattern),
                Company.notes.ilike(pattern),
            )
        )

    total = query.count()

    order = _SORT_MAP.get(sort_by, Company.created_at.desc())
    query = query.order_by(order)

    offset = (page - 1) * page_size
    companies = query.offset(offset).limit(page_size).all()

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

        # Duplicate detection: case-insensitive name match
        existing = (
            db.query(Company)
            .filter(func.lower(Company.name) == name.lower())
            .first()
        )
        if existing:
            rows.append(
                BulkImportRow(
                    row=idx,
                    company_name=name,
                    status="duplicate",
                    detail=f"Company '{name}' already exists (id={existing.id})",
                )
            )
            duplicates += 1
            continue

        try:
            result = create_company(db, data)
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