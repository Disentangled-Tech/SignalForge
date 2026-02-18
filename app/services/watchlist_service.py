"""Watchlist service — add, remove, list with composite and 7-day delta (Issue #94)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Company, ReadinessSnapshot, Watchlist
from app.schemas.watchlist import WatchlistItemResponse


class WatchlistConflictError(ValueError):
    """Raised when adding a company that is already on the watchlist."""

    pass


def add_to_watchlist(
    db: Session,
    company_id: int,
    reason: str | None = None,
) -> Watchlist | None:
    """Add a company to the watchlist.

    If company does not exist, returns None (caller should return 404).
    If active entry already exists, raises WatchlistConflictError (caller returns 409).
    If inactive entry exists, reactivates it and updates reason.
    Otherwise creates a new Watchlist entry.

    Returns the Watchlist entry.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None

    existing_active = (
        db.query(Watchlist)
        .filter(Watchlist.company_id == company_id, Watchlist.is_active == True)
        .first()
    )
    if existing_active:
        raise WatchlistConflictError("Company is already on the watchlist")

    existing_inactive = (
        db.query(Watchlist)
        .filter(Watchlist.company_id == company_id, Watchlist.is_active == False)
        .first()
    )
    if existing_inactive:
        existing_inactive.is_active = True
        existing_inactive.added_reason = reason
        db.commit()
        db.refresh(existing_inactive)
        return existing_inactive

    entry = Watchlist(company_id=company_id, added_reason=reason, is_active=True)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def remove_from_watchlist(db: Session, company_id: int) -> bool:
    """Remove a company from the watchlist (soft delete: set is_active=False).

    Returns True if an active entry was found and removed, False otherwise.
    """
    entry = (
        db.query(Watchlist)
        .filter(Watchlist.company_id == company_id, Watchlist.is_active == True)
        .first()
    )
    if not entry:
        return False
    entry.is_active = False
    db.commit()
    return True


def list_watchlist(db: Session, as_of: date | None = None) -> list[WatchlistItemResponse]:
    """List active watchlist entries with latest composite and 7-day delta.

    For each entry: fetches latest ReadinessSnapshot (as_of <= as_of_date),
    snapshot 7 days before that as_of, computes delta_7d = latest - prev.
    Returns list of WatchlistItemResponse.
    """
    if as_of is None:
        as_of = date.today()

    entries = (
        db.query(Watchlist)
        .filter(Watchlist.is_active == True)
        .join(Company, Watchlist.company_id == Company.id)
        .order_by(Watchlist.added_at.desc())
        .all()
    )

    result: list[WatchlistItemResponse] = []
    prev_date = as_of - timedelta(days=7)

    for entry in entries:
        company = entry.company

        latest_snap = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id == company.id,
                ReadinessSnapshot.as_of <= as_of,
            )
            .order_by(ReadinessSnapshot.as_of.desc())
            .first()
        )

        latest_composite: int | None = latest_snap.composite if latest_snap else None
        delta_7d: int | None = None

        if latest_snap:
            prev_snap = (
                db.query(ReadinessSnapshot)
                .filter(
                    ReadinessSnapshot.company_id == company.id,
                    ReadinessSnapshot.as_of == prev_date,
                )
                .first()
            )
            if prev_snap is not None:
                delta_7d = latest_snap.composite - prev_snap.composite
            else:
                delta_7d = 0  # No snapshot 7 days ago; treat as no change

        result.append(
            WatchlistItemResponse(
                company_id=company.id,
                company_name=company.name,
                website_url=company.website_url,
                added_at=entry.added_at,
                added_reason=entry.added_reason,
                latest_composite=latest_composite,
                delta_7d=delta_7d,
            )
        )

    return result
