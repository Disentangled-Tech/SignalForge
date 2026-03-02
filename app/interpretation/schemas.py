"""LLM Event Interpretation schemas (Issue #281, M1).

Defines InterpretationInput (content + evidence for classification) and
InterpretationOutput (list of items mapping 1:1 to CoreEventCandidate with
optional snippet). event_type must be from core taxonomy only; validation
uses existing is_valid_core_event_type / CoreEventCandidate contract.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.core_events import CoreEventCandidate
from app.schemas.scout import EvidenceItem


class InterpretationInput(BaseModel):
    """Input to the LLM Event Interpretation layer.

    content: Raw text to classify (e.g. diff, evidence text).
    evidence: Optional list of EvidenceItem for source_refs (0-based indices).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(..., min_length=1, description="Raw content to classify")
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence items for source-backed mapping (source_refs)",
    )


class InterpretationOutputItem(CoreEventCandidate):
    """One interpreted event: CoreEventCandidate shape plus optional snippet.

    event_type must be in core taxonomy. Optional snippet holds the supporting
    text for this event (e.g. quoted passage). Use to_core_event_candidate()
    to obtain the canonical CoreEventCandidate for extractor/verification.
    """

    snippet: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional supporting snippet for this event",
    )

    def to_core_event_candidate(self) -> CoreEventCandidate:
        """Return a CoreEventCandidate with the same event fields (no snippet)."""
        return CoreEventCandidate(
            event_type=self.event_type,
            event_time=self.event_time,
            title=self.title,
            summary=self.summary,
            url=self.url,
            confidence=self.confidence,
            source_refs=self.source_refs,
        )


InterpretationOutput = list[InterpretationOutputItem]
