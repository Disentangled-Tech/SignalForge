"""Outreach API schemas (Issue #108, #115, #122)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.outreach_recommendation import OutreachRecommendation


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


class OutreachRecommendationResponse(BaseModel):
    """Response schema for GET /api/outreach/recommendation/{company_id} (Issue #122 M1).

    Recommended playbook ID, draft variants, rationale, sensitivity tag, and core
    recommendation fields. Rationale is derived from recommendation_type and safeguards.
    """

    company_id: int
    as_of: date
    recommended_playbook_id: str
    drafts: list[dict] = Field(
        default_factory=list, description="Draft variants (subject, message)"
    )
    rationale: str = Field(description="Why this outreach approach")
    sensitivity_tag: str | None = None
    recommendation_type: str
    outreach_score: int
    safeguards_triggered: list | None = None
    pack_id: UUID | None = None
    id: int | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": False}


def ore_recommendation_to_response(
    rec: OutreachRecommendation,
    *,
    sensitivity_tag: str | None = None,
) -> OutreachRecommendationResponse:
    """Map OutreachRecommendation ORM to API response (Issue #122 M1).

    Rationale is derived from recommendation_type and safeguards_triggered.
    sensitivity_tag may be provided from ESL context when building response.
    """
    if not isinstance(rec, OutreachRecommendation):
        raise TypeError("rec must be OutreachRecommendation")
    parts = [f"Recommendation: {rec.recommendation_type}."]
    if rec.safeguards_triggered:
        parts.append(" Safeguards: " + "; ".join(str(s) for s in rec.safeguards_triggered))
    rationale = " ".join(parts).strip()
    return OutreachRecommendationResponse(
        company_id=rec.company_id,
        as_of=rec.as_of,
        recommended_playbook_id=(rec.playbook_id or ""),
        drafts=list(rec.draft_variants) if rec.draft_variants else [],
        rationale=rationale,
        sensitivity_tag=sensitivity_tag,
        recommendation_type=rec.recommendation_type,
        outreach_score=rec.outreach_score,
        safeguards_triggered=rec.safeguards_triggered,
        pack_id=rec.pack_id,
        id=rec.id,
        created_at=rec.created_at,
    )


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
