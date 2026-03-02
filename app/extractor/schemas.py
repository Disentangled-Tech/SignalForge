"""Extractor result and JSON schema for extraction output (M2, Issue #277).

ExtractionResult is the in-memory output of the Evidence Extractor: normalized
entities (Company, Person) and Core Event candidates only. Serializable to
structured_payload shape for Evidence Store. Strict JSON schema exported for
LLM/API validation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.core_events import (
    CoreEventCandidate,
    ExtractionEntityCompany,
    ExtractionEntityPerson,
)

# Version for structured_payload compatibility (Step 3)
EXTRACTION_PAYLOAD_VERSION = "1.0"


class ExtractionResult(BaseModel):
    """Result of extracting entities and core event candidates from an Evidence Bundle.

    All events are source-backed (source_refs = 0-based indices into bundle.evidence).
    Pack-agnostic: same bundle → same result. No signal derivation.
    """

    model_config = ConfigDict(extra="forbid")

    company: ExtractionEntityCompany | None = Field(
        None,
        description="Normalized company from bundle or raw extraction",
    )
    person: ExtractionEntityPerson | None = Field(
        None,
        description="Normalized person when provided by raw extraction",
    )
    core_event_candidates: list[CoreEventCandidate] = Field(
        default_factory=list,
        description="Core event candidates only; event_type validated against core taxonomy",
    )
    version: str = Field(
        default=EXTRACTION_PAYLOAD_VERSION,
        description="Payload version for store/repository compatibility",
    )


def extraction_result_json_schema() -> dict[str, Any]:
    """Return strict JSON schema for extraction output (for LLM or API validation)."""
    return ExtractionResult.model_json_schema()
