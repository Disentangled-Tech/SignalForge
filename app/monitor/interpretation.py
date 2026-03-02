"""Monitor LLM interpretation (M5): ChangeEvent → list[CoreEventCandidate].

Calls LLM with diff summary; validates event_type against core taxonomy; drops invalid.
Pack-agnostic; no raw observation text passed to LLM beyond structured diff summary/snippets.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.core_taxonomy.loader import get_core_signal_ids
from app.extractor.validation import is_valid_core_event_type
from app.monitor.schemas import ChangeEvent
from app.prompts.loader import render_prompt
from app.schemas.core_events import CoreEventCandidate

# CoreEventCandidate.summary max_length; truncate LLM snippet to avoid silent drop
SUMMARY_MAX_LENGTH = 2000

if TYPE_CHECKING:
    from app.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# Cap candidates per change event (align with extractor MAX_CORE_EVENT_CANDIDATES)
MAX_CANDIDATES_PER_CHANGE = 50


def interpret_change_event(
    change_event: ChangeEvent,
    *,
    llm_provider: LLMProvider | None = None,
) -> list[CoreEventCandidate]:
    """Interpret a change event via LLM and return validated Core Event candidates.

    Calls LLM with prompt that accepts diff summary and page URL; requires JSON
    output with core_event_candidates (event_type, snippet, confidence). Each
    event_type is validated with is_valid_core_event_type; invalid types are dropped.
    source_refs = [0] (single change event = one source).

    Args:
        change_event: Structured change event from diff detection.
        llm_provider: LLM provider. If None, uses get_llm_provider(role=ModelRole.JSON).

    Returns:
        List of validated CoreEventCandidate; empty on parse failure or when all invalid.
    """
    from app.llm.router import ModelRole, get_llm_provider

    core_signal_ids = get_core_signal_ids()
    core_event_types_str = ", ".join(sorted(core_signal_ids))

    prompt = render_prompt(
        "monitor_event_interpretation_v1",
        CORE_EVENT_TYPES=core_event_types_str,
        PAGE_URL=change_event.page_url,
        DIFF_SUMMARY=change_event.diff_summary,
    )

    provider = llm_provider or get_llm_provider(role=ModelRole.JSON)
    raw = provider.complete(
        prompt,
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    parsed = _parse_llm_response(raw)
    if parsed is None:
        return []

    raw_candidates = parsed.get("core_event_candidates")
    if not isinstance(raw_candidates, list):
        return []

    candidates: list[CoreEventCandidate] = []
    for item in raw_candidates[:MAX_CANDIDATES_PER_CHANGE]:
        if not isinstance(item, dict):
            continue
        event_type = item.get("event_type")
        if not isinstance(event_type, str) or not event_type.strip():
            continue
        if not is_valid_core_event_type(event_type.strip()):
            logger.debug("Monitor interpretation: dropping invalid event_type %r", event_type)
            continue
        snippet = item.get("snippet")
        raw_summary = snippet if isinstance(snippet, str) else None
        summary = (raw_summary or "")[:SUMMARY_MAX_LENGTH] or None
        confidence_raw = item.get("confidence")
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else 0.5
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        try:
            candidates.append(
                CoreEventCandidate(
                    event_type=event_type.strip(),
                    event_time=None,
                    title=None,
                    summary=summary,
                    url=change_event.page_url,
                    confidence=confidence,
                    source_refs=[0],
                )
            )
        except ValidationError:
            logger.debug("Monitor interpretation: failed to build CoreEventCandidate for %r", item)
            continue
    return candidates


def _parse_llm_response(raw: str) -> dict | None:
    """Parse LLM response as JSON. Returns None on failure."""
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Monitor interpretation: LLM response was not valid JSON")
        return None
    if not isinstance(data, dict):
        return None
    return data
