"""LLM Event Interpretation for Scout (M3/M4, Issue #281).

Takes an Evidence Bundle (content + evidence) and returns validated CoreEventCandidate list.
Pack-agnostic; no raw observation text passed to LLM beyond hypothesis and evidence snippets.
"""

from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)

# Cap candidates per bundle (align with extractor MAX_CORE_EVENT_CANDIDATES)
MAX_CANDIDATES_PER_BUNDLE = 50


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
        logger.warning("Scout interpretation: LLM response was not valid JSON")
        return None
    if not isinstance(data, dict):
        return None
    return data


def interpret_bundle_to_core_events(
    bundle: EvidenceBundle,
    *,
    llm_provider: LLMProvider | None = None,
) -> list[CoreEventCandidate]:
    """Interpret an evidence bundle via LLM and return validated Core Event candidates.

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
