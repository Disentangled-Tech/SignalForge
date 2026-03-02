"""Tests for LLM Event Interpretation module (M3 — Issue #281).

Unit tests with mock LLM: valid JSON → CoreEventCandidate list; unknown event_type
dropped; malformed JSON → empty; schema validation. Calibration: output only contains
core taxonomy event types.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.core_taxonomy.loader import get_core_signal_ids
from app.interpretation.llm import interpret_to_core_events
from app.schemas.core_events import CoreEventCandidate
from app.schemas.scout import EvidenceItem


def _evidence_item(index: int = 0) -> EvidenceItem:
    return EvidenceItem(
        url=f"https://example.com/{index}",
        quoted_snippet=f"Snippet {index}",
        timestamp_seen=datetime.now(UTC),
        source_type="web",
        confidence_score=0.9,
    )


def test_interpret_to_core_events_returns_candidates_when_llm_valid() -> None:
    """When LLM returns valid core event types, interpret_to_core_events returns CoreEventCandidates."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "cto_role_posted",
                    "snippet": "CTO role posted.",
                    "confidence": 0.9,
                    "source_refs": [0],
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Company is hiring a CTO.",
        evidence=[_evidence_item(0)],
        llm_provider=mock_llm,
    )

    assert len(result) == 1
    assert isinstance(result[0], CoreEventCandidate)
    assert result[0].event_type == "cto_role_posted"
    assert result[0].summary == "CTO role posted."
    assert result[0].confidence == 0.9
    assert result[0].source_refs == [0]


def test_interpret_to_core_events_drops_invalid_event_types() -> None:
    """When LLM returns mix of valid and invalid event types, invalid ones are dropped."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "funding_raised",
                    "snippet": "Series A.",
                    "confidence": 0.8,
                    "source_refs": [0],
                },
                {
                    "event_type": "unknown_foo",
                    "snippet": "x",
                    "confidence": 0.5,
                    "source_refs": [1],
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0), _evidence_item(1)],
        llm_provider=mock_llm,
    )

    assert len(result) == 1
    assert result[0].event_type == "funding_raised"


def test_interpret_to_core_events_rejects_unknown_event_type() -> None:
    """Interpretation rejects unknown event_type; only valid core types returned."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "not_in_taxonomy",
                    "snippet": "nope",
                    "confidence": 0.9,
                    "source_refs": [0],
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0)],
        llm_provider=mock_llm,
    )

    assert result == []


def test_interpret_to_core_events_empty_list_when_llm_returns_empty_candidates() -> None:
    """When LLM returns empty core_event_candidates, result is empty list."""
    raw = json.dumps({"core_event_candidates": []})
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[],
        llm_provider=mock_llm,
    )

    assert result == []


def test_interpret_to_core_events_malformed_json_returns_empty_list() -> None:
    """When LLM returns invalid JSON, interpret_to_core_events returns empty list."""
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value="not json at all")

    result = interpret_to_core_events(
        content="Content",
        evidence=[],
        llm_provider=mock_llm,
    )

    assert result == []


def test_interpret_to_core_events_missing_core_event_candidates_key_returns_empty_list() -> None:
    """When LLM returns JSON without core_event_candidates key, result is empty list."""
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value='{"other": []}')

    result = interpret_to_core_events(
        content="Content",
        evidence=[],
        llm_provider=mock_llm,
    )

    assert result == []


def test_interpret_to_core_events_uses_prompt_with_content_and_evidence() -> None:
    """interpret_to_core_events passes CONTENT and evidence to the prompt."""
    raw = json.dumps({"core_event_candidates": []})
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)
    evidence = [_evidence_item(0)]

    interpret_to_core_events(
        content="Specific content to classify.",
        evidence=evidence,
        llm_provider=mock_llm,
    )

    mock_llm.complete.assert_called_once()
    call_args = mock_llm.complete.call_args
    prompt = call_args[0][0]
    assert "Specific content to classify." in prompt
    assert "Snippet 0" in prompt
    assert "CORE_EVENT_TYPES" in prompt or "funding_raised" in prompt


def test_interpret_to_core_events_multiple_valid_candidates() -> None:
    """Multiple valid candidates are all returned with correct source_refs."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "funding_raised",
                    "snippet": "Series A.",
                    "confidence": 0.8,
                    "source_refs": [0],
                },
                {
                    "event_type": "cto_role_posted",
                    "snippet": "CTO role.",
                    "confidence": 0.85,
                    "source_refs": [1],
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0), _evidence_item(1)],
        llm_provider=mock_llm,
    )

    assert len(result) == 2
    assert result[0].event_type == "funding_raised"
    assert result[0].source_refs == [0]
    assert result[1].event_type == "cto_role_posted"
    assert result[1].source_refs == [1]


def test_interpret_to_core_events_calls_llm_with_json_response_format() -> None:
    """LLM is called with response_format json_object and low temperature."""
    raw = json.dumps({"core_event_candidates": []})
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    interpret_to_core_events(content="x", evidence=[], llm_provider=mock_llm)

    mock_llm.complete.assert_called_once()
    kwargs = mock_llm.complete.call_args[1]
    assert kwargs.get("response_format") == {"type": "json_object"}
    assert kwargs.get("temperature", 1) <= 0.5


def test_interpret_to_core_events_calibration_only_core_taxonomy_event_types() -> None:
    """All returned event_type values are in core taxonomy (calibration)."""
    core_ids = list(get_core_signal_ids())[:3]
    if not core_ids:
        pytest.skip("No core signal_ids in taxonomy")
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": core_ids[0],
                    "snippet": "Supporting text",
                    "confidence": 0.8,
                    "source_refs": [0],
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0)],
        llm_provider=mock_llm,
    )

    assert len(result) == 1
    assert result[0].event_type in get_core_signal_ids()


def test_interpret_to_core_events_optional_title_summary_url_preserved() -> None:
    """Optional title, summary, url from LLM are preserved when valid."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "funding_raised",
                    "snippet": "Raised Series A.",
                    "confidence": 0.9,
                    "source_refs": [0],
                    "title": "Series A",
                    "summary": "Company raised Series A.",
                    "url": "https://example.com/news",
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0)],
        llm_provider=mock_llm,
    )

    assert len(result) == 1
    assert result[0].title == "Series A"
    assert result[0].summary == "Company raised Series A."
    assert result[0].url == "https://example.com/news"


def test_interpret_to_core_events_truncates_long_snippet_to_summary_max_length() -> None:
    """When LLM returns snippet longer than CoreEventCandidate.summary max_length, summary is truncated."""
    max_len = 2000  # CoreEventCandidate.summary max_length
    long_snippet = "x" * (max_len + 500)
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "funding_raised",
                    "snippet": long_snippet,
                    "confidence": 0.8,
                    "source_refs": [0],
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0)],
        llm_provider=mock_llm,
    )

    assert len(result) == 1
    assert result[0].summary is not None
    assert len(result[0].summary) <= max_len
    assert result[0].summary == long_snippet[:max_len]


def test_interpret_to_core_events_skips_non_dict_items_in_candidates() -> None:
    """When LLM returns list with non-dict items, they are skipped."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "funding_raised",
                    "snippet": "Ok",
                    "confidence": 0.8,
                    "source_refs": [0],
                },
                "not a dict",
                None,
                42,
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0)],
        llm_provider=mock_llm,
    )

    assert len(result) == 1
    assert result[0].event_type == "funding_raised"


def test_interpret_to_core_events_confidence_invalid_fallback_to_half() -> None:
    """When confidence is not a number, fallback to 0.5."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "funding_raised",
                    "snippet": "Ok",
                    "confidence": "high",
                    "source_refs": [0],
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0)],
        llm_provider=mock_llm,
    )

    assert len(result) == 1
    assert result[0].confidence == 0.5


def test_interpret_to_core_events_source_refs_accepts_whole_number_floats() -> None:
    """source_refs can contain whole-number floats and are converted to int."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "funding_raised",
                    "snippet": "Ok",
                    "confidence": 0.8,
                    "source_refs": [0.0, 1.0],
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0), _evidence_item(1)],
        llm_provider=mock_llm,
    )

    assert len(result) == 1
    assert result[0].source_refs == [0, 1]


def test_interpret_to_core_events_event_time_iso_parsed() -> None:
    """event_time ISO 8601 string is parsed and set."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "funding_raised",
                    "snippet": "Ok",
                    "confidence": 0.8,
                    "source_refs": [0],
                    "event_time": "2025-03-01T12:00:00+00:00",
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0)],
        llm_provider=mock_llm,
    )

    assert len(result) == 1
    assert result[0].event_time is not None
    assert result[0].event_time.isoformat().startswith("2025-03-01")


def test_interpret_to_core_events_event_time_invalid_ignored() -> None:
    """Invalid event_time string is ignored (event_time stays None)."""
    raw = json.dumps(
        {
            "core_event_candidates": [
                {
                    "event_type": "funding_raised",
                    "snippet": "Ok",
                    "confidence": 0.8,
                    "source_refs": [0],
                    "event_time": "not-a-date",
                },
            ],
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_to_core_events(
        content="Content",
        evidence=[_evidence_item(0)],
        llm_provider=mock_llm,
    )

    assert len(result) == 1
    assert result[0].event_time is None


def test_interpret_to_core_events_empty_evidence_block_in_prompt() -> None:
    """When evidence is empty, EVIDENCE_BLOCK is (no evidence items)."""
    raw = json.dumps({"core_event_candidates": []})
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    interpret_to_core_events(content="Only content.", evidence=[], llm_provider=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "(no evidence items)" in prompt
