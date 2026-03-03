"""Calibration tests for LLM Event Interpretation (M5 — Issue #281).

Fixture: fixed content + evidence (ChangeEvent); run interpretation with mock LLM.
Assert: all returned event_type in core taxonomy; no new types; optional stability.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core_taxonomy.loader import get_core_signal_ids
from app.extractor.validation import is_valid_core_event_type
from app.interpretation.schemas import InterpretationOutputItem
from app.monitor.interpretation import interpret_change_event
from app.monitor.schemas import ChangeEvent

# --- Fixtures ---


@pytest.fixture
def fixed_change_event() -> ChangeEvent:
    """Fixed ChangeEvent for calibration: stable diff summary and URL."""
    return ChangeEvent(
        page_url="https://example.com/careers",
        timestamp=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
        diff_summary="New job posting for CTO added. Company raised Series A.",
        before_hash="hash_before",
        after_hash="hash_after",
        snippet_before=None,
        snippet_after=None,
        company_id=1,
        source_type=None,
    )


def _mock_llm_returning(raw_json: str) -> MagicMock:
    """Build a mock LLM that returns the given JSON string."""
    mock = MagicMock()
    mock.complete = MagicMock(return_value=raw_json)
    return mock


# --- Calibration: all returned event_type in core taxonomy ---


def test_calibration_all_returned_event_types_in_core_taxonomy(
    fixed_change_event: ChangeEvent,
) -> None:
    """Interpretation returns only event_type values that are in core taxonomy."""
    core_ids = get_core_signal_ids()
    # Use a subset that we know exists
    valid_types = ["funding_raised", "cto_role_posted", "job_posted_engineering"]
    assert all(t in core_ids for t in valid_types)
    raw = json.dumps(
        {
            "core_event_candidates": [
                {"event_type": t, "snippet": f"Snippet for {t}.", "confidence": 0.8}
                for t in valid_types
            ]
        }
    )
    mock_llm = _mock_llm_returning(raw)

    result = interpret_change_event(fixed_change_event, llm_provider=mock_llm)

    assert len(result) == len(valid_types)
    for candidate in result:
        assert candidate.event_type in core_ids
        assert is_valid_core_event_type(candidate.event_type)


def test_calibration_no_new_types_returned(fixed_change_event: ChangeEvent) -> None:
    """Interpretation never returns event_type outside core taxonomy (invalid dropped)."""
    # LLM returns one valid and one invalid; only valid should appear in result
    raw = json.dumps(
        {
            "core_event_candidates": [
                {"event_type": "funding_raised", "snippet": "Series A.", "confidence": 0.9},
                {"event_type": "invented_type", "snippet": "Nope.", "confidence": 0.5},
            ]
        }
    )
    mock_llm = _mock_llm_returning(raw)

    result = interpret_change_event(fixed_change_event, llm_provider=mock_llm)

    core_ids = get_core_signal_ids()
    assert len(result) == 1
    assert result[0].event_type == "funding_raised"
    assert result[0].event_type in core_ids
    # Explicit: no event in result has a type outside taxonomy
    for c in result:
        assert c.event_type in core_ids, "Calibration: no new event types allowed"


def test_calibration_output_event_types_subset_of_taxonomy(
    fixed_change_event: ChangeEvent,
) -> None:
    """The set of returned event_type is always a subset of get_core_signal_ids()."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {"event_type": "cto_role_posted", "snippet": "CTO role.", "confidence": 0.85},
            ]
        }
    )
    mock_llm = _mock_llm_returning(raw)

    result = interpret_change_event(fixed_change_event, llm_provider=mock_llm)

    core_ids = get_core_signal_ids()
    returned_types = {c.event_type for c in result}
    assert returned_types <= core_ids
    assert len(returned_types) <= len(core_ids)


# --- Calibration: schema-level (InterpretationOutputItem only core types) ---


def test_calibration_interpretation_output_item_only_accepts_core_types() -> None:
    """InterpretationOutputItem accepts only event_type from core taxonomy (no new types)."""
    core_ids = get_core_signal_ids()
    for signal_id in list(core_ids)[:5]:  # sample
        item = InterpretationOutputItem(
            event_type=signal_id,
            event_time=None,
            title=None,
            summary=None,
            url=None,
            confidence=0.5,
            source_refs=[],
            snippet=None,
        )
        assert item.event_type == signal_id
        assert item.event_type in core_ids


def test_calibration_interpretation_output_item_rejects_non_taxonomy_type() -> None:
    """InterpretationOutputItem rejects event_type not in core taxonomy (Pydantic validator)."""
    with pytest.raises(ValidationError):
        InterpretationOutputItem(
            event_type="not_in_core_taxonomy",
            event_time=None,
            title=None,
            summary=None,
            url=None,
            confidence=0.5,
            source_refs=[],
            snippet=None,
        )


# --- Calibration: stability (same input + mock → same allowed output) ---


def test_calibration_same_input_same_mock_same_event_types(
    fixed_change_event: ChangeEvent,
) -> None:
    """With fixed input and mock LLM, interpretation returns same set of event types (determinism)."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {"event_type": "funding_raised", "snippet": "Raised.", "confidence": 0.8},
                {"event_type": "cto_role_posted", "snippet": "CTO.", "confidence": 0.85},
            ]
        }
    )
    mock_llm = _mock_llm_returning(raw)

    result1 = interpret_change_event(fixed_change_event, llm_provider=mock_llm)
    result2 = interpret_change_event(fixed_change_event, llm_provider=mock_llm)

    types1 = {c.event_type for c in result1}
    types2 = {c.event_type for c in result2}
    assert types1 == types2
    assert types1 <= get_core_signal_ids()
