"""Ranked companies schemas for GET /api/companies/top (Issue #247)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RankedCompanyTop(BaseModel):
    """Single ranked company for Daily Briefing (Issue #247)."""

    company_id: int
    company_name: str
    website_url: str | None = None
    composite_score: int
    recommendation_band: str | None = None  # IGNORE | WATCH | HIGH_PRIORITY
    top_signals: list[str] = Field(default_factory=list)  # top 3 human labels
    # Optional dimension breakdown for UI
    momentum: int | None = None
    complexity: int | None = None
    pressure: int | None = None
    leadership_gap: int | None = None


class RankedCompaniesResponse(BaseModel):
    """Response for GET /api/companies/top."""

    companies: list[RankedCompanyTop]
    total: int
