"""Watchlist schemas for request/response validation (Issue #94)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WatchlistAddRequest(BaseModel):
    """Schema for adding a company to the watchlist."""

    company_id: int = Field(..., gt=0)
    reason: str | None = Field(None, max_length=500)


class WatchlistItemResponse(BaseModel):
    """Schema for a watchlist item in the list response."""

    company_id: int
    company_name: str
    website_url: str | None
    added_at: datetime
    added_reason: str | None
    latest_composite: int | None
    delta_7d: int | None

    model_config = ConfigDict(from_attributes=True)


class WatchlistListResponse(BaseModel):
    """Schema for the watchlist list response."""

    items: list[WatchlistItemResponse]
