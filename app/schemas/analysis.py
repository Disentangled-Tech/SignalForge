"""Analysis schemas for stage classification and pain signal output."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PainSignalItem(BaseModel):
    """A single pain signal: value (bool) with reasoning. Matches LLM output format."""

    value: bool = False
    why: str = ""


class PainSignals(BaseModel):
    """The 7 boolean pain signal fields from the analysis pipeline (LLM output keys)."""

    model_config = ConfigDict(extra="allow")

    hiring_engineers: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Company is hiring for technical roles",
    )
    switching_from_agency: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Mentions agency, contractors, bringing in-house",
    )
    adding_enterprise_features: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="SSO, RBAC, audit logs, SLAs, multi-tenant",
    )
    compliance_security_pressure: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="SOC2, HIPAA, ISO, vendor security questionnaires",
    )
    product_delivery_issues: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Missed timelines, slipping, hard to ship, bug volume",
    )
    architecture_scaling_risk: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Rewrites, performance bottlenecks, outgrowing stack",
    )
    founder_overload: PainSignalItem = Field(
        default_factory=PainSignalItem,
        description="Burnout posts, wearing too many hats, looking for technical leadership",
    )


class AnalysisRecordRead(BaseModel):
    """Schema for reading an analysis record (response)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    stage: str | None = None
    stage_confidence: float | None = Field(None, ge=0.0, le=1.0)
    pain_signals: PainSignals | None = None
    evidence_bullets: list[str] | None = None
    explanation: str | None = None
    created_at: datetime


class AnalysisRecordList(BaseModel):
    """Paginated list of analysis records."""

    items: list[AnalysisRecordRead]
    total: int
    page: int = 1
    page_size: int = 20

