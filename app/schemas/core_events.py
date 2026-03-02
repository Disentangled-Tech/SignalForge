"""Core Event and extraction entity schemas (Extractor M1 — Issue #277).

Pydantic models for Core Event candidates and normalized entities emitted by the
Extractor. event_type is validated against core taxonomy only. All extracted
fields/events are source-backed (source_refs = 0-based indices into evidence).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.extractor.validation import is_valid_core_event_type


class CoreEventCandidate(BaseModel):
    """A single core event candidate from extraction (no signal derivation).

    event_type must be in core taxonomy. source_refs are 0-based indices
    into the evidence list (EvidenceBundle.evidence) for source-backed audit.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_type: str = Field(..., min_length=1, max_length=128)
    event_time: datetime | None = Field(None)
    title: str | None = Field(None, max_length=500)
    summary: str | None = Field(None, max_length=2000)
    url: str | None = Field(None, max_length=2048)
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_refs: list[int] = Field(
        default_factory=list,
        description="0-based indices into bundle.evidence for source-backed mapping",
    )

    @field_validator("event_type")
    @classmethod
    def event_type_must_be_core(cls, v: str) -> str:
        if not is_valid_core_event_type(v):
            raise ValueError(
                f"event_type must be a core taxonomy signal_id; got: {v!r}"
            )
        return v


class ExtractionEntityCompany(BaseModel):
    """Normalized company fields from extraction (nullable for unsupported)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255)
    domain: str | None = Field(None, max_length=255)
    website_url: str | None = Field(None, max_length=2048)


class ExtractionEntityPerson(BaseModel):
    """Normalized person fields from extraction (nullable for unsupported)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255)
    role: str | None = Field(None, max_length=128)
