"""LLM Event Interpretation (M3, Issue #281): content + evidence → list[CoreEventCandidate].

Calls LLM with strict structured-output prompt; parses and validates output against
core taxonomy; drops invalid event types; logs candidate counts and latency.
Pack-agnostic; no raw observation text passed beyond content and evidence snippets.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.core_taxonomy.loader import get_core_signal_ids
from app.extractor.validation import is_valid_core_event_type
from app.prompts.loader import render_prompt
from app.schemas.core_events import CoreEventCandidate

if TYPE_CHECKING:
    from app.llm.provider import LLMProvider
    from app.schemas.scout import EvidenceItem

logger = logging.getLogger(__name__)

# CoreEventCandidate.summary max_length; truncate LLM snippet to avoid validation failure
SUMMARY_MAX_LENGTH = 2000

# Cap candidates per interpretation call (align with extractor MAX_CORE_EVENT_CANDIDATES)
MAX_CANDIDATES_PER_INTERPRETATION = 50


def interpret_to_core_events(
    content: str,
    evidence: list[EvidenceItem],
    *,
    llm_provider: LLMProvider,
) -> list[CoreEventCandidate]:
    """Interpret content via LLM and return validated Core Event candidates.

    Renders event_interpretation_v1 prompt with content and evidence; calls LLM
    with JSON response format; parses core_event_candidates; validates each
    event_type with is_valid_core_event_type (drops invalid); maps snippet to
    summary (truncated). Logs candidate count before/after validation and latency.

    Args:
        content: Raw text to classify (e.g. evidence text, diff summary).
        evidence: List of EvidenceItem for source_refs (0-based indices).
        llm_provider: LLM provider instance (required).

    Returns:
        List of validated CoreEventCandidate; empty on parse failure or when all invalid.
    """
    core_signal_ids = get_core_signal_ids()
    core_event_types_str = ", ".join(sorted(core_signal_ids))
    evidence_block = _format_evidence_block(evidence)

    prompt = render_prompt(
        "event_interpretation_v1",
        CORE_EVENT_TYPES=core_event_types_str,
        CONTENT=content,
        EVIDENCE_BLOCK=evidence_block,
    )

    start = time.monotonic()
    raw = llm_provider.complete(
        prompt,
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    parsed = _parse_llm_response(raw)
    if parsed is None:
        logger.warning("Interpretation LLM response was not valid JSON")
        return []

    raw_candidates = parsed.get("core_event_candidates")
    if not isinstance(raw_candidates, list):
        return []

    raw_count = len(raw_candidates)
    candidates: list[CoreEventCandidate] = []
    for item in raw_candidates[:MAX_CANDIDATES_PER_INTERPRETATION]:
        if not isinstance(item, dict):
            continue
        candidate = _item_to_core_event_candidate(item)
        if candidate is None:
            continue
        candidates.append(candidate)

    logger.info(
        "Interpretation: raw_candidates=%d valid=%d latency_ms=%d",
        raw_count,
        len(candidates),
        latency_ms,
    )
    return candidates


def _format_evidence_block(evidence: list[EvidenceItem]) -> str:
    """Format evidence list for prompt: [index] url / quoted_snippet."""
    if not evidence:
        return "(no evidence items)"
    lines = []
    for i, item in enumerate(evidence):
        snippet = (item.quoted_snippet or "").strip() or item.url
        lines.append(f"[{i}] {snippet}")
    return "\n".join(lines)


def _parse_llm_response(raw: str) -> dict | None:
    """Parse LLM response as JSON. Returns None on failure."""
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _item_to_core_event_candidate(item: dict) -> CoreEventCandidate | None:
    """Build CoreEventCandidate from one LLM output item; return None if invalid."""
    event_type = item.get("event_type")
    if not isinstance(event_type, str) or not event_type.strip():
        return None
    event_type = event_type.strip()
    if not is_valid_core_event_type(event_type):
        logger.debug("Interpretation: dropping invalid event_type %r", event_type)
        return None

    snippet = item.get("snippet")
    raw_summary = item.get("summary")
    if isinstance(raw_summary, str) and raw_summary.strip():
        summary = raw_summary.strip()[:SUMMARY_MAX_LENGTH] or None
    elif isinstance(snippet, str) and snippet.strip():
        summary = snippet.strip()[:SUMMARY_MAX_LENGTH] or None
    else:
        summary = None

    confidence_raw = item.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw is not None else 0.5
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    source_refs_raw = item.get("source_refs")
    source_refs: list[int] = []
    if isinstance(source_refs_raw, list):
        for x in source_refs_raw:
            if isinstance(x, int) and x >= 0:
                source_refs.append(x)
            elif isinstance(x, float) and x == int(x) and x >= 0:
                source_refs.append(int(x))

    title = item.get("title")
    title = title.strip()[:500] if isinstance(title, str) and title.strip() else None
    url = item.get("url")
    url = url.strip()[:2048] if isinstance(url, str) and url.strip() else None

    event_time = None
    et_raw = item.get("event_time")
    if isinstance(et_raw, str) and et_raw.strip():
        try:
            from datetime import datetime

            event_time = datetime.fromisoformat(et_raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    try:
        return CoreEventCandidate(
            event_type=event_type,
            event_time=event_time,
            title=title,
            summary=summary,
            url=url,
            confidence=confidence,
            source_refs=source_refs,
        )
    except ValidationError:
        logger.debug("Interpretation: failed to build CoreEventCandidate for %r", item)
        return None
