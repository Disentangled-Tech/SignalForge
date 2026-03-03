"""Core Event and extraction entity schemas (Extractor M1/M3 — Issue #277).

Pydantic models for Core Event candidates and normalized entities emitted by the
Extractor. event_type is validated against core taxonomy only. All extracted
fields/events are source-backed (source_refs = 0-based indices into evidence).

M3: Structured payload contract — ExtractionClaim and StructuredExtractionPayload
define the schema for extractor output stored in evidence_bundles.structured_payload.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CoreEventCandidate(BaseModel):
    """A single core event candidate from extraction (no signal derivation).

    event_type must be in core taxonomy. source_refs are 0-based indices
    into the evidence list (EvidenceBundle.evidence) for source-backed audit.
    This is the canonical event shape; LLM Event Interpretation output maps to
    CoreEventCandidate (Issue #281).
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
        from app.extractor.validation import is_valid_core_event_type

        if not is_valid_core_event_type(v):
            raise ValueError(f"event_type must be a core taxonomy signal_id; got: {v!r}")
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


# ── Payload key compatibility (M2: events vs core_event_candidates) ──────────
#
# TODO(M2 follow-up): (1) Decide contract when both keys exist and events==[]: currently
# we use core_event_candidates (events is falsy). If product requires "always prefer
# events key when present", use: raw = payload.get("events") if "events" in payload
# else payload.get("core_event_candidates"). (2) Add integration test: store bundle
# with ExtractionResult-shaped structured_payload and run verification (and seeder).
# (3) Docstring: state that when both exist and events is [], we return
# core_event_candidates (prefer = "events if truthy else core_event_candidates").


def get_events_from_payload(payload: dict | None) -> list[dict]:
    """Return list of event dicts from structured_payload.

    Accepts both ExtractionResult shape (core_event_candidates) and
    StructuredExtractionPayload shape (events). Prefers 'events' when both present.
    Returns only list items that are dicts; empty list if missing or not a list.
    """
    if not payload:
        return []
    raw = payload.get("events") or payload.get("core_event_candidates")
    if not isinstance(raw, list):
        return []
    return [e for e in raw if isinstance(e, dict)]


# ── M3: Structured payload contract ─────────────────────────────────────────

# Reasonable upper bound for claim value (DB is Text; limit for validation and consistency)
EXTRACTION_CLAIM_VALUE_MAX_LENGTH = 10_000


class ExtractionClaim(BaseModel):
    """Single claim for evidence_claims; source_refs are 0-based indices into evidence.

    Stored in StructuredExtractionPayload.claims; serialized to the dict shape
    expected by evidence store (store_evidence_bundle) for claims insertion.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_type: str = Field(..., min_length=1, max_length=64)
    field: str = Field(..., max_length=255)
    value: str | None = Field(None, max_length=EXTRACTION_CLAIM_VALUE_MAX_LENGTH)
    source_refs: list[int] = Field(
        default_factory=list,
        description="0-based indices into bundle.evidence for source-backed mapping",
    )
    confidence: float | None = Field(None, ge=0.0, le=1.0)


class StructuredExtractionPayload(BaseModel):
    """Structured payload contract for extractor output (M3).

    Emitted by the extractor; can be stored in evidence_bundles.structured_payload.
    model_dump(mode='json') produces a dict compatible with store_evidence_bundle
    (including payload['claims'] for evidence_claims insertion).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: str = Field(default="1.0", min_length=1, max_length=32)
    events: list[CoreEventCandidate] = Field(default_factory=list)
    company: ExtractionEntityCompany | None = Field(None)
    persons: list[ExtractionEntityPerson] = Field(default_factory=list)
    claims: list[ExtractionClaim] = Field(default_factory=list)
