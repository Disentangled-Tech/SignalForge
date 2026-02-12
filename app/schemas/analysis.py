"""Analysis schemas for stage classification and pain signal output."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PainSignalItem(BaseModel):
    """A single pain signal: detected (bool) with reasoning."""

    detected: bool = False
    why: str = ""


class PainSignals(BaseModel):
    """The 7 boolean pain signal fields from the analysis pipeline."""

    hiring_technical_roles: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Company is hiring for technical roles",
    )
    recent_funding: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Company recently received funding",
    )
    product_launch: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Company is launching or has launched a product",
    )
    technical_debt_indicators: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Signs of technical debt or legacy systems",
    )
    scaling_challenges: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Company facing scaling challenges",
    )
    leadership_changes: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Recent leadership or CTO changes",
    )
    compliance_needs: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Regulatory or compliance requirements",
    )


class AnalysisRecordRead(BaseModel):
    """Schema for reading an analysis record (response)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    stage: Optional[str] = None
    stage_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    pain_signals: Optional[PainSignals] = None
    evidence_bullets: Optional[list[str]] = None
    explanation: Optional[str] = None
    created_at: datetime


class AnalysisRecordList(BaseModel):
    """Paginated list of analysis records."""

    items: list[AnalysisRecordRead]
    total: int
    page: int = 1
    page_size: int = 20

