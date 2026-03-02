"""Tests for LLM Event Interpretation schemas (M1 — Issue #281).

Unit tests: InterpretationInput/InterpretationOutput types; validation against
core taxonomy; unknown event_type rejected; schema bounds.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core_taxonomy.loader import get_core_signal_ids
from app.interpretation.schemas import (
    InterpretationInput,
    InterpretationOutput,
    InterpretationOutputItem,
)
from app.schemas.scout import EvidenceItem

# --- InterpretationInput ---


def test_interpretation_input_accepts_content_and_evidence() -> None:
    """InterpretationInput accepts content and list of EvidenceItem."""
    evidence = [
        EvidenceItem(
            url="https://example.com/1",
            quoted_snippet="Snippet one",
            timestamp_seen=datetime.now(UTC),
            source_type="web",
            confidence_score=0.9,
        ),
    ]
    obj = InterpretationInput(content="Some raw content to classify.", evidence=evidence)
    assert obj.content == "Some raw content to classify."
    assert len(obj.evidence) == 1
    assert obj.evidence[0].quoted_snippet == "Snippet one"


def test_interpretation_input_accepts_empty_evidence() -> None:
    """InterpretationInput allows empty evidence (content-only interpretation)."""
    obj = InterpretationInput(content="Content only.", evidence=[])
    assert obj.content == "Content only."
    assert obj.evidence == []


def test_interpretation_input_forbids_extra_fields() -> None:
    """InterpretationInput forbids extra fields."""
    with pytest.raises(ValidationError):
        InterpretationInput(
            content="x",
            evidence=[],
            extra_key="not_allowed",
        )


# --- InterpretationOutputItem ---


def test_interpretation_output_item_valid_minimal() -> None:
    """InterpretationOutputItem accepts minimal valid fields with valid event_type."""
    obj = InterpretationOutputItem(
        event_type="funding_raised",
        event_time=None,
        title=None,
        summary=None,
        url=None,
        confidence=0.9,
        source_refs=[0],
        snippet=None,
    )
    assert obj.event_type == "funding_raised"
    assert obj.confidence == 0.9
    assert obj.snippet is None


def test_interpretation_output_item_valid_with_snippet() -> None:
    """InterpretationOutputItem accepts optional snippet."""
    obj = InterpretationOutputItem(
        event_type="cto_role_posted",
        event_time=None,
        title=None,
        summary=None,
        url=None,
        confidence=0.85,
        source_refs=[0],
        snippet="Company is hiring a CTO.",
    )
    assert obj.snippet == "Company is hiring a CTO."
    assert obj.event_type == "cto_role_posted"


def test_interpretation_output_item_rejects_unknown_event_type() -> None:
    """InterpretationOutputItem rejects event_type not in core taxonomy."""
    with pytest.raises(ValidationError) as exc_info:
        InterpretationOutputItem(
            event_type="not_in_taxonomy",
            event_time=None,
            title=None,
            summary=None,
            url=None,
            confidence=0.5,
            source_refs=[0],
            snippet=None,
        )
    errors = exc_info.value.errors()
    assert any("event_type" in (e.get("loc") or ()) for e in errors)


def test_interpretation_output_item_event_type_from_core_taxonomy_only() -> None:
    """All returned event_type values must be in core taxonomy (explicit set check)."""
    for signal_id in get_core_signal_ids():
        obj = InterpretationOutputItem(
            event_type=signal_id,
            event_time=None,
            title=None,
            summary=None,
            url=None,
            confidence=0.5,
            source_refs=[],
            snippet=None,
        )
        assert obj.event_type == signal_id


def test_interpretation_output_item_maps_to_core_event_candidate() -> None:
    """InterpretationOutputItem can be converted to CoreEventCandidate (same fields)."""
    from app.schemas.core_events import CoreEventCandidate

    item = InterpretationOutputItem(
        event_type="funding_raised",
        event_time=None,
        title="Series A",
        summary="Raised Series A.",
        url="https://example.com",
        confidence=0.9,
        source_refs=[0, 1],
        snippet="Optional snippet not in CoreEventCandidate.",
    )
    candidate = item.to_core_event_candidate()
    assert isinstance(candidate, CoreEventCandidate)
    assert candidate.event_type == item.event_type
    assert candidate.confidence == item.confidence
    assert candidate.source_refs == item.source_refs
    assert candidate.title == item.title
    assert not hasattr(candidate, "snippet")


# --- InterpretationOutput (list of InterpretationOutputItem) ---


def test_interpretation_output_valid_list() -> None:
    """InterpretationOutput is a list of valid InterpretationOutputItem."""
    output: InterpretationOutput = [
        InterpretationOutputItem(
            event_type="funding_raised",
            event_time=None,
            title=None,
            summary=None,
            url=None,
            confidence=0.8,
            source_refs=[0],
            snippet=None,
        ),
    ]
    assert len(output) == 1
    assert output[0].event_type == "funding_raised"


def test_interpretation_output_schema_bounds_snippet_optional() -> None:
    """Snippet is optional; other bounds same as CoreEventCandidate."""
    # confidence in [0, 1]
    InterpretationOutputItem(
        event_type="funding_raised",
        event_time=None,
        title=None,
        summary=None,
        url=None,
        confidence=0.0,
        source_refs=[],
        snippet=None,
    )
    InterpretationOutputItem(
        event_type="funding_raised",
        event_time=None,
        title=None,
        summary=None,
        url=None,
        confidence=1.0,
        source_refs=[],
        snippet="",
    )
    with pytest.raises(ValidationError):
        InterpretationOutputItem(
            event_type="funding_raised",
            event_time=None,
            title=None,
            summary=None,
            url=None,
            confidence=1.1,
            source_refs=[],
            snippet=None,
        )
