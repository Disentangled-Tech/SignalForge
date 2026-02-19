"""Briefing schemas for daily briefing output (Issue #110)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.company import CompanyRead


class BriefingItemRead(BaseModel):
    """A single briefing entry with company info and outreach draft."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company: CompanyRead
    stage: Optional[str] = None
    why_now: Optional[str] = None
    risk_summary: Optional[str] = None
    suggested_angle: Optional[str] = None
    outreach_subject: Optional[str] = None
    outreach_message: Optional[str] = None
    briefing_date: date
    created_at: Optional[datetime] = None

    # ESL fields (Issue #110) — optional when EngagementSnapshot missing
    esl_score: Optional[float] = None
    outreach_score: Optional[int] = None
    outreach_recommendation: Optional[str] = None
    cadence_blocked: Optional[bool] = None
    stability_cap_triggered: Optional[bool] = None


class EmergingCompanyBriefing(BaseModel):
    """Single company in Emerging Companies to Watch section (Issue #110)."""

    company_id: int
    company_name: str
    website_url: Optional[str] = None
    outreach_score: int
    esl_score: float
    engagement_type: str
    cadence_blocked: bool = False
    stability_cap_triggered: bool = False
    top_signals: list[str] = Field(default_factory=list)
    trs: Optional[int] = None
    momentum: Optional[int] = None
    complexity: Optional[int] = None
    pressure: Optional[int] = None
    leadership_gap: Optional[int] = None


class BriefingResponse(BaseModel):
    """Daily briefing response containing multiple items (Issue #110)."""

    date: date
    items: list[BriefingItemRead]
    emerging_companies: list[EmergingCompanyBriefing] = Field(default_factory=list)
    total: int = 0

