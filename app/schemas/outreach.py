"""Outreach API schemas (Issue #108, #114)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class OutreachHistoryRead(BaseModel):
    """Single outreach record for API (Issue #114)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    outreach_type: str
    sent_at: datetime
    outcome: str | None = None
    timing_quality_feedback: str | None = None
    message: str | None = None
    notes: str | None = None
    created_at: datetime


class OutreachHistoryList(BaseModel):
    """List of outreach records for a company."""

    items: list[OutreachHistoryRead]


class OutreachHistoryUpdate(BaseModel):
    """PATCH body for updating outreach record (Issue #114)."""

    outcome: str | None = None
    notes: str | None = None
    timing_quality_feedback: str | None = None


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
