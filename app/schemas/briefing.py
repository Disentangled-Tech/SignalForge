"""Briefing schemas for daily briefing output."""

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


class BriefingResponse(BaseModel):
    """Daily briefing response containing multiple items."""

    date: date
    items: list[BriefingItemRead]
    total: int = 0

