"""Tests for monitor LLM interpretation (M5): interpret_change_event → CoreEventCandidate.

Unit tests with mocked LLM: valid/invalid event types, drop invalid, reject unknown event_type.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.monitor.interpretation import interpret_change_event
from app.monitor.schemas import ChangeEvent
from app.schemas.core_events import CoreEventCandidate


def _change_event(
    page_url: str = "https://example.com/blog",
    diff_summary: str = "New job posting for CTO added.",
) -> ChangeEvent:
    return ChangeEvent(
        page_url=page_url,
        timestamp=datetime.now(UTC),
        diff_summary=diff_summary,
        before_hash=None,
        after_hash=None,
        snippet_before=None,
        snippet_after=None,
    )


def test_interpret_change_event_returns_candidates_when_llm_returns_valid_types() -> None:
    """When LLM returns valid core event types, interpret_change_event returns CoreEventCandidates."""
    raw = '{"core_event_candidates": [{"event_type": "cto_role_posted", "snippet": "CTO role posted.", "confidence": 0.9}]}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_change_event(_change_event(), llm_provider=mock_llm)

    assert len(result) == 1
    assert isinstance(result[0], CoreEventCandidate)
    assert result[0].event_type == "cto_role_posted"
    assert result[0].summary == "CTO role posted."
    assert result[0].confidence == 0.9
    assert result[0].source_refs == [0]


def test_interpret_change_event_drops_invalid_event_types() -> None:
    """When LLM returns mix of valid and invalid event types, invalid ones are dropped."""
    raw = '{"core_event_candidates": [{"event_type": "funding_raised", "snippet": "Series A.", "confidence": 0.8}, {"event_type": "unknown_foo", "snippet": "x", "confidence": 0.5}]}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_change_event(_change_event(), llm_provider=mock_llm)

    assert len(result) == 1
    assert result[0].event_type == "funding_raised"


def test_interpret_change_event_rejects_unknown_event_type() -> None:
    """Interpretation rejects unknown event_type via is_valid_core_event_type (only valid returned)."""
    raw = '{"core_event_candidates": [{"event_type": "not_in_taxonomy", "snippet": "nope", "confidence": 0.9}]}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_change_event(_change_event(), llm_provider=mock_llm)

    assert len(result) == 0


def test_interpret_change_event_empty_list_when_llm_returns_empty_candidates() -> None:
    """When LLM returns empty core_event_candidates, result is empty list."""
    raw = '{"core_event_candidates": []}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_change_event(_change_event(), llm_provider=mock_llm)

    assert result == []


def test_interpret_change_event_malformed_json_returns_empty_list() -> None:
    """When LLM returns invalid JSON, interpret_change_event returns empty list."""
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value="not json at all")

    result = interpret_change_event(_change_event(), llm_provider=mock_llm)

    assert result == []


def test_interpret_change_event_missing_core_event_candidates_key_returns_empty_list() -> None:
    """When LLM returns JSON without core_event_candidates key, result is empty list."""
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value='{"other": []}')

    result = interpret_change_event(_change_event(), llm_provider=mock_llm)

    assert result == []


def test_interpret_change_event_uses_render_prompt_with_change_event_fields() -> None:
    """interpret_change_event passes PAGE_URL and DIFF_SUMMARY to the prompt."""
    raw = '{"core_event_candidates": []}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)
    ev = _change_event(page_url="https://company.com/careers", diff_summary="New role: VP Eng.")

    interpret_change_event(ev, llm_provider=mock_llm)

    mock_llm.complete.assert_called_once()
    call_args = mock_llm.complete.call_args
    prompt = call_args[0][0]
    assert "https://company.com/careers" in prompt
    assert "New role: VP Eng." in prompt
    assert "CORE_EVENT_TYPES" in prompt or "funding_raised" in prompt  # taxonomy in prompt


def test_interpret_change_event_multiple_valid_candidates() -> None:
    """Multiple valid candidates are all returned with source_refs [0]."""
    raw = '{"core_event_candidates": [{"event_type": "funding_raised", "snippet": "Series A.", "confidence": 0.8}, {"event_type": "cto_role_posted", "snippet": "CTO role.", "confidence": 0.85}]}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_change_event(_change_event(), llm_provider=mock_llm)

    assert len(result) == 2
    assert result[0].event_type == "funding_raised"
    assert result[1].event_type == "cto_role_posted"
    for c in result:
        assert c.source_refs == [0]


# CoreEventCandidate.summary max_length; must match app.monitor.interpretation.SUMMARY_MAX_LENGTH
_SUMMARY_MAX_LENGTH = 2000


def test_interpret_change_event_truncates_long_snippet_to_summary_max_length() -> None:
    """When LLM returns snippet longer than CoreEventCandidate.summary max_length, summary is truncated."""
    long_snippet = "x" * (_SUMMARY_MAX_LENGTH + 500)
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "funding_raised",
                    "snippet": long_snippet,
                    "confidence": 0.8,
                }
            ]
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_change_event(_change_event(), llm_provider=mock_llm)

    assert len(result) == 1
    assert result[0].event_type == "funding_raised"
    assert result[0].summary is not None
    assert len(result[0].summary) == _SUMMARY_MAX_LENGTH
    assert result[0].summary == "x" * _SUMMARY_MAX_LENGTH
