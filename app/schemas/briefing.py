"""Briefing schemas for daily briefing output (Issue #110)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.company import CompanyRead


class BriefingItemRead(BaseModel):
    """A single briefing entry with company info and outreach draft."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company: CompanyRead
    stage: str | None = None
    why_now: str | None = None
    risk_summary: str | None = None
    suggested_angle: str | None = None
    outreach_subject: str | None = None
    outreach_message: str | None = None
    briefing_date: date
    created_at: datetime | None = None

    # ESL fields (Issue #110) — optional when EngagementSnapshot missing
    esl_score: float | None = None
    outreach_score: int | None = None
    outreach_recommendation: str | None = None
    cadence_blocked: bool | None = None
    stability_cap_triggered: bool | None = None
    # Issue #175 Phase 3 — ESL gate
    esl_decision: str | None = None
    sensitivity_level: str | None = None


class EmergingCompanyBriefing(BaseModel):
    """Single company in Emerging Companies to Watch section (Issue #110)."""

    company_id: int
    company_name: str
    website_url: str | None = None
    outreach_score: int
    esl_score: float
    engagement_type: str
    cadence_blocked: bool = False
    stability_cap_triggered: bool = False
    top_signals: list[str] = Field(default_factory=list)
    # Issue #175 Phase 3 — ESL gate
    esl_decision: str | None = None
    sensitivity_level: str | None = None
    trs: int | None = None
    momentum: int | None = None
    complexity: int | None = None
    pressure: int | None = None
    leadership_gap: int | None = None
    # Issue #242 Phase 3 — pack recommendation band when available
    recommendation_band: str | None = None


class BriefingResponse(BaseModel):
    """Daily briefing response containing multiple items (Issue #110)."""

    date: date
    items: list[BriefingItemRead]
    emerging_companies: list[EmergingCompanyBriefing] = Field(default_factory=list)
    total: int = 0
