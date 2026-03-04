"""Outreach API schemas (Issue #108, #115)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OutreachRecommendationRead(BaseModel):
    """Read schema for a single ORE-generated recommendation (Issue #115 M4, future API)."""

    id: int
    company_id: int
    as_of: date
    recommendation_type: str
    outreach_score: int
    channel: str | None = None
    draft_variants: list[dict] | None = None
    strategy_notes: dict | None = None
    safeguards_triggered: list | None = None
    generation_version: str | None = None
    pack_id: UUID | None = None
    playbook_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


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
