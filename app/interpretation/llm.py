"""LLM Event Interpretation (M3/M4, Issue #281).

M3: interpret_to_core_events(content, evidence) — generic content + evidence → list[CoreEventCandidate].
M4 Scout: interpret_bundle_to_core_events(bundle) — Evidence Bundle → list[CoreEventCandidate].
Calls LLM with strict structured-output prompt; parses and validates against core taxonomy.
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
from app.schemas.scout import EvidenceBundle

# CoreEventCandidate.summary max_length; truncate snippet to avoid silent drop
SUMMARY_MAX_LENGTH = 2000

if TYPE_CHECKING:
    from app.llm.provider import LLMProvider
    from app.schemas.scout import EvidenceItem

logger = logging.getLogger(__name__)

# Cap candidates per interpretation call (align with extractor MAX_CORE_EVENT_CANDIDATES)
MAX_CANDIDATES_PER_BUNDLE = 50
MAX_CANDIDATES_PER_INTERPRETATION = 50


def _bundle_content_for_prompt(bundle: EvidenceBundle) -> str:
    """Build content string: why_now_hypothesis plus numbered evidence snippets."""
    parts: list[str] = []
    if bundle.why_now_hypothesis and bundle.why_now_hypothesis.strip():
        parts.append(f"Hypothesis: {bundle.why_now_hypothesis.strip()}")
    for i, e in enumerate(bundle.evidence):
        parts.append(f"[{i}] {e.quoted_snippet.strip()}")
    return "\n\n".join(parts) if parts else "(no content)"


def _parse_llm_response(raw: str) -> dict | None:
    """Parse LLM response as JSON. Returns None on failure."""
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Interpretation: LLM response was not valid JSON")
        return None
    if not isinstance(data, dict):
        return None
    return data


def _format_evidence_block(evidence: list) -> str:
    """Format evidence list for prompt: [index] url / quoted_snippet."""
    if not evidence:
        return "(no evidence items)"
    lines = []
    for i, item in enumerate(evidence):
        snippet = (getattr(item, "quoted_snippet", None) or "").strip() or getattr(item, "url", "")
        lines.append(f"[{i}] {snippet}")
    return "\n".join(lines)


def interpret_to_core_events(
    content: str,
    evidence: list,
    *,
    llm_provider: "LLMProvider",
) -> list[CoreEventCandidate]:
    """Interpret content via LLM and return validated Core Event candidates.

    Renders event_interpretation_v1 prompt with content and evidence; calls LLM
    with JSON response format; parses core_event_candidates; validates each
    event_type with is_valid_core_event_type (drops invalid). Logs candidate count
    and latency.

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


def interpret_bundle_to_core_events(
    bundle: EvidenceBundle,
    *,
    llm_provider: "LLMProvider | None" = None,
) -> list[CoreEventCandidate]:
    """Interpret an evidence bundle via LLM and return validated Core Event candidates (M4 Scout).

    Builds content from why_now_hypothesis and evidence snippets; calls LLM with
    scout_event_interpretation_v1 prompt. Each event_type is validated with
    is_valid_core_event_type; invalid types and invalid source_refs are dropped.
    source_refs are 0-based indices into bundle.evidence.

    Args:
        bundle: Scout Evidence Bundle (validated).
        llm_provider: LLM provider. If None, uses get_llm_provider(role=ModelRole.JSON).

    Returns:
        List of validated CoreEventCandidate; empty on parse failure or when all invalid.
    """
    from app.llm.router import ModelRole, get_llm_provider

    evidence_len = len(bundle.evidence)
    core_signal_ids = get_core_signal_ids()
    core_event_types_str = ", ".join(sorted(core_signal_ids))
    content = _bundle_content_for_prompt(bundle)

    prompt = render_prompt(
        "scout_event_interpretation_v1",
        CORE_EVENT_TYPES=core_event_types_str,
        CONTENT=content,
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
    for item in raw_candidates[:MAX_CANDIDATES_PER_BUNDLE]:
        if not isinstance(item, dict):
            continue
        event_type = item.get("event_type")
        if not isinstance(event_type, str) or not event_type.strip():
            continue
        if not is_valid_core_event_type(event_type.strip()):
            logger.debug(
                "Scout interpretation: dropping invalid event_type %r",
                event_type,
            )
            continue
        source_refs_raw = item.get("source_refs")
        if isinstance(source_refs_raw, list):
            source_refs = [
                r for r in source_refs_raw if isinstance(r, int) and 0 <= r < evidence_len
            ]
        else:
            source_refs = []
        snippet = item.get("snippet")
        raw_summary = snippet if isinstance(snippet, str) else None
        summary = (raw_summary or "")[:SUMMARY_MAX_LENGTH] or None
        confidence_raw = item.get("confidence")
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else 0.5
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        url: str | None = None
        if len(source_refs) == 1 and source_refs[0] < len(bundle.evidence):
            url = bundle.evidence[source_refs[0]].url or None
        try:
            candidates.append(
                CoreEventCandidate(
                    event_type=event_type.strip(),
                    event_time=None,
                    title=None,
                    summary=summary,
                    url=url,
                    confidence=confidence,
                    source_refs=source_refs,
                )
            )
        except ValidationError:
            logger.debug(
                "Scout interpretation: failed to build CoreEventCandidate for %r",
                item,
            )
            continue
    return candidates
