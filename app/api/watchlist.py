"""Watchlist API routes (Issue #94)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_auth
from app.db.session import get_db
from app.schemas.watchlist import WatchlistAddRequest, WatchlistListResponse
from app.services.watchlist_service import (
    WatchlistConflictError,
    add_to_watchlist,
    list_watchlist,
    remove_from_watchlist,
)

router = APIRouter()


@router.post("", status_code=201)
def api_add_to_watchlist(
    data: WatchlistAddRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> dict:
    """Add a company to the watchlist."""
    try:
        result = add_to_watchlist(db, data.company_id, data.reason)
    except WatchlistConflictError:
        raise HTTPException(
            status_code=409,
            detail="Company is already on the watchlist",
        )
    if result is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"company_id": result.company_id, "added_at": result.added_at.isoformat()}


@router.delete("/{company_id}", status_code=204)
def api_remove_from_watchlist(
    company_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> None:
    """Remove a company from the watchlist."""
    removed = remove_from_watchlist(db, company_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Company not on watchlist")


@router.get("", response_model=WatchlistListResponse)
def api_list_watchlist(
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
) -> WatchlistListResponse:
    """List watchlist entries with latest composite and 7-day delta."""
    items = list_watchlist(db)
    return WatchlistListResponse(items=items)
