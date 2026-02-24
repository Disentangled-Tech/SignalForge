"""Outreach API schemas (Issue #108)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class OutreachReviewItem(BaseModel):
    """Single company in the weekly outreach review."""

    company_id: int
    company_name: str
    website_url: str | None
    outreach_score: int
    explain: dict = Field(default_factory=dict)


class OutreachReviewResponse(BaseModel):
    """Response for GET /api/outreach/review."""

    as_of: date
    companies: list[OutreachReviewItem]
