"""Scout (LLM Discovery) schemas — Evidence Bundles only, no signals or domain entities.

Per plan: Evidence-Only Mode; strict validation; JSON schema export for LLM output validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ── Evidence item (single citation) ─────────────────────────────────────────


class EvidenceItem(BaseModel):
    """Single evidence citation: url, quoted snippet, timestamp, source type, confidence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(..., min_length=1, max_length=2048)
    quoted_snippet: str = Field(..., min_length=1, max_length=2000)
    timestamp_seen: datetime
    source_type: str = Field(..., min_length=1, max_length=64)
    confidence_score: float = Field(..., ge=0.0, le=1.0)


# ── Evidence bundle (per-candidate output) ───────────────────────────────────


class EvidenceBundle(BaseModel):
    """Structured scout output for one candidate: company, hypothesis, evidence, missing info.

    No signal_id, event_type, or pack-specific fields. Citation rule: when why_now_hypothesis
    is non-empty, evidence must be non-empty (claims must be backed by citations).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    candidate_company_name: str = Field(..., min_length=1, max_length=255)
    company_website: str = Field(..., min_length=1, max_length=2048)
    why_now_hypothesis: str = Field("", max_length=2000)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=50)
    missing_information: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def citation_required_when_claim(self) -> EvidenceBundle:
        """Require at least one evidence item when why_now_hypothesis is non-empty."""
        if self.why_now_hypothesis and self.why_now_hypothesis.strip() and not self.evidence:
            raise ValueError(
                "evidence must be non-empty when why_now_hypothesis is provided (citation requirement)"
            )
        return self


# ── Scout run input ─────────────────────────────────────────────────────────


class ScoutRunInput(BaseModel):
    """Input for a discovery scout run: ICP, exclusion rules, optional pack_id."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    icp_definition: str = Field(..., min_length=1, max_length=4000)
    exclusion_rules: str | None = Field(None, max_length=2000)
    pack_id: str | None = Field(None, max_length=64)


class RunScoutRequest(BaseModel):
    """Request body for POST /internal/run_scout."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    icp_definition: str = Field(..., min_length=1, max_length=4000)
    exclusion_rules: str | None = Field(None, max_length=2000)
    pack_id: str | None = Field(None, max_length=64)
    page_fetch_limit: int = Field(10, ge=0, le=100)
    workspace_id: uuid.UUID | None = Field(
        None,
        description="Workspace to scope this run; stored on scout_runs for tenant boundary.",
    )


# ── Scout run result (response) ─────────────────────────────────────────────


class ScoutRunMetadata(BaseModel):
    """Metadata for a scout run: model version, tokens, latency, page count."""

    model_config = ConfigDict(extra="forbid")

    model_version: str = Field(..., min_length=1, max_length=128)
    tokens_used: int | None = Field(None, ge=0)
    latency_ms: int | None = Field(None, ge=0)
    page_fetch_count: int = Field(0, ge=0)


class ScoutRunResult(BaseModel):
    """Result of a scout run: run_id, validated bundles, metadata."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., min_length=1, max_length=64)
    bundles: list[EvidenceBundle] = Field(default_factory=list)
    metadata: ScoutRunMetadata


def evidence_bundle_json_schema() -> dict[str, Any]:
    """Return JSON schema for EvidenceBundle (for LLM output validation)."""
    return EvidenceBundle.model_json_schema()
