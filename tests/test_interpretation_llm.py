"""Tests for Scout LLM interpretation (M3/M4): interpret_bundle_to_core_events → CoreEventCandidate.

Unit tests with mocked LLM: valid/invalid event types, drop invalid, malformed JSON.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.interpretation.llm import (
    _bundle_content_for_prompt,
    _parse_llm_response,
    interpret_bundle_to_core_events,
)
from app.schemas.core_events import CoreEventCandidate
from app.schemas.scout import EvidenceBundle, EvidenceItem


def _evidence_bundle(
    why_now: str = "Recently hiring engineers.",
    evidence_snippets: list[str] | None = None,
) -> EvidenceBundle:
    if evidence_snippets is None:
        evidence_snippets = ["We are hiring senior engineers."]
    evidence = [
        EvidenceItem(
            url="https://example.com/careers",
            quoted_snippet=s,
            timestamp_seen=datetime.now(UTC),
            source_type="careers",
            confidence_score=0.9,
        )
        for s in evidence_snippets
    ]
    return EvidenceBundle(
        candidate_company_name="Acme Inc",
        company_website="https://acme.com",
        why_now_hypothesis=why_now,
        evidence=evidence,
        missing_information=[],
    )


def test_bundle_content_for_prompt_includes_hypothesis_and_evidence() -> None:
    """_bundle_content_for_prompt builds content from why_now and numbered evidence."""
    bundle = _evidence_bundle(why_now="Hiring.", evidence_snippets=["Snippet one."])
    content = _bundle_content_for_prompt(bundle)
    assert "Hypothesis: Hiring." in content
    assert "[0]" in content
    assert "Snippet one." in content


def test_bundle_content_for_prompt_empty_hypothesis_and_evidence_yields_no_content() -> None:
    """_bundle_content_for_prompt with empty hypothesis and empty evidence yields (no content)."""
    bundle = EvidenceBundle(
        candidate_company_name="Acme",
        company_website="https://acme.com",
        why_now_hypothesis="",
        evidence=[],
        missing_information=[],
    )
    content = _bundle_content_for_prompt(bundle)
    assert content == "(no content)"


def test_bundle_content_for_prompt_no_hypothesis_uses_evidence_only() -> None:
    """_bundle_content_for_prompt with empty why_now uses evidence snippets only."""
    bundle = _evidence_bundle(why_now="", evidence_snippets=["Only snippet."])
    content = _bundle_content_for_prompt(bundle)
    assert "[0]" in content
    assert "Only snippet." in content


def test_parse_llm_response_valid_json() -> None:
    """_parse_llm_response returns dict for valid JSON."""
    raw = '{"core_event_candidates": [{"event_type": "funding_raised"}]}'
    assert _parse_llm_response(raw) == {"core_event_candidates": [{"event_type": "funding_raised"}]}


def test_parse_llm_response_invalid_json_returns_none() -> None:
    """_parse_llm_response returns None for invalid JSON."""
    assert _parse_llm_response("not json") is None
    assert _parse_llm_response("") is None
    assert _parse_llm_response("   ") is None


def test_parse_llm_response_non_dict_returns_none() -> None:
    """_parse_llm_response returns None when root is not a dict."""
    assert _parse_llm_response("[1,2,3]") is None


def test_interpret_bundle_to_core_events_returns_candidates_when_llm_valid() -> None:
    """When LLM returns valid core event types, interpret_bundle_to_core_events returns CoreEventCandidates."""
    raw = '{"core_event_candidates": [{"event_type": "funding_raised", "snippet": "Series A.", "confidence": 0.9, "source_refs": [0]}]}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_bundle_to_core_events(_evidence_bundle(), llm_provider=mock_llm)

    assert len(result) == 1
    assert isinstance(result[0], CoreEventCandidate)
    assert result[0].event_type == "funding_raised"
    assert result[0].summary == "Series A."
    assert result[0].confidence == 0.9
    assert result[0].source_refs == [0]


def test_interpret_bundle_to_core_events_drops_invalid_event_types() -> None:
    """When LLM returns mix of valid and invalid event types, invalid ones are dropped."""
    raw = '{"core_event_candidates": [{"event_type": "funding_raised", "snippet": "Series A.", "confidence": 0.8}, {"event_type": "unknown_foo", "snippet": "x", "confidence": 0.5}]}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_bundle_to_core_events(_evidence_bundle(), llm_provider=mock_llm)

    assert len(result) == 1
    assert result[0].event_type == "funding_raised"


def test_interpret_bundle_to_core_events_rejects_unknown_event_type() -> None:
    """Interpretation rejects unknown event_type via is_valid_core_event_type."""
    raw = '{"core_event_candidates": [{"event_type": "not_in_taxonomy", "snippet": "nope", "confidence": 0.9}]}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_bundle_to_core_events(_evidence_bundle(), llm_provider=mock_llm)

    assert len(result) == 0


def test_interpret_bundle_to_core_events_empty_list_when_llm_returns_empty_candidates() -> None:
    """When LLM returns empty core_event_candidates, result is empty list."""
    raw = '{"core_event_candidates": []}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_bundle_to_core_events(_evidence_bundle(), llm_provider=mock_llm)

    assert result == []


def test_interpret_bundle_to_core_events_malformed_json_returns_empty_list() -> None:
    """When LLM returns invalid JSON, interpret_bundle_to_core_events returns empty list."""
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value="not json at all")

    result = interpret_bundle_to_core_events(_evidence_bundle(), llm_provider=mock_llm)

    assert result == []


def test_interpret_bundle_to_core_events_missing_core_event_candidates_key_returns_empty_list() -> (
    None
):
    """When LLM returns JSON without core_event_candidates key, result is empty list."""
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value='{"other": []}')

    result = interpret_bundle_to_core_events(_evidence_bundle(), llm_provider=mock_llm)

    assert result == []


def test_interpret_bundle_to_core_events_uses_render_prompt_with_content_and_core_types() -> None:
    """interpret_bundle_to_core_events passes CONTENT and CORE_EVENT_TYPES to the prompt."""
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value='{"core_event_candidates": []}')
    with patch("app.interpretation.llm.render_prompt") as mock_render:
        interpret_bundle_to_core_events(_evidence_bundle(why_now="Hiring."), llm_provider=mock_llm)
    mock_render.assert_called_once()
    call_kw = mock_render.call_args[1]
    assert "CONTENT" in call_kw
    assert "Hiring." in call_kw["CONTENT"]
    assert "CORE_EVENT_TYPES" in call_kw


def test_interpret_bundle_to_core_events_source_refs_out_of_range_dropped() -> None:
    """source_refs beyond evidence length are filtered out."""
    raw = '{"core_event_candidates": [{"event_type": "funding_raised", "snippet": "OK", "confidence": 0.8, "source_refs": [0, 99]}]}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)
    bundle = _evidence_bundle(evidence_snippets=["one"])  # only index 0 valid

    result = interpret_bundle_to_core_events(bundle, llm_provider=mock_llm)

    assert len(result) == 1
    assert result[0].source_refs == [0]


def test_interpret_bundle_to_core_events_single_source_ref_sets_url_from_evidence() -> None:
    """When source_refs has one valid index, url is taken from that evidence item."""
    raw = '{"core_event_candidates": [{"event_type": "job_posted_engineering", "snippet": "Hiring.", "confidence": 0.9, "source_refs": [0]}]}'
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)
    bundle = _evidence_bundle(evidence_snippets=["We are hiring."])

    result = interpret_bundle_to_core_events(bundle, llm_provider=mock_llm)

    assert len(result) == 1
    assert result[0].url == "https://example.com/careers"


def test_interpret_bundle_to_core_events_multiple_valid_candidates() -> None:
    """Multiple valid candidates are all returned."""
    core_ids = __import__(
        "app.core_taxonomy.loader", fromlist=["get_core_signal_ids"]
    ).get_core_signal_ids()
    ids = sorted(core_ids)[:2]
    raw = json.dumps(
        {
            "core_event_candidates": [
                {"event_type": ids[0], "snippet": "A", "confidence": 0.8, "source_refs": [0]},
                {"event_type": ids[1], "snippet": "B", "confidence": 0.7, "source_refs": [0]},
            ]
        }
    )
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=raw)

    result = interpret_bundle_to_core_events(_evidence_bundle(), llm_provider=mock_llm)

    assert len(result) == 2
    assert result[0].event_type == ids[0]
    assert result[1].event_type == ids[1]


def test_interpret_bundle_to_core_events_uses_provider_when_passed() -> None:
    """When llm_provider is passed, get_llm_provider is not called."""
    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value='{"core_event_candidates": []}')
    with patch("app.llm.router.get_llm_provider") as mock_get:
        interpret_bundle_to_core_events(_evidence_bundle(), llm_provider=mock_llm)
    mock_get.assert_not_called()
    mock_llm.complete.assert_called_once()
