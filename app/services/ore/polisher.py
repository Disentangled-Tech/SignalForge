"""ORE polisher — optional LLM polishing step (Issue #119 M2).

Polishes an existing draft for readability and flow only; does not add claims,
urgency, or references to signals outside allowed_framing_labels.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from app.llm.router import ModelRole, get_llm_provider
from app.prompts.loader import resolve_prompt_content

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)

_EMPTY_DRAFT = {"subject": "", "message": ""}


def _parse_json_safe(text: str) -> dict | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _build_tone_instruction(
    tone_definition: str | None,
    sensitivity_level: str | None,
) -> str:
    """Build TONE_INSTRUCTION for polish prompt from tone_definition + sensitivity_level."""
    parts: list[str] = []
    if sensitivity_level and isinstance(sensitivity_level, str) and sensitivity_level.strip():
        parts.append(f"Sensitivity: {sensitivity_level.strip()}.")
    if tone_definition and tone_definition.strip():
        parts.append(tone_definition.strip())
    return " ".join(parts).strip() if parts else ""


def polish_ore_draft(
    subject: str,
    message: str,
    *,
    tone_definition: str | None = None,
    sensitivity_level: str | None = None,
    forbidden_phrases: list[str] | None = None,
    allowed_framing_labels: list[str] | None = None,
    pack: Pack | None = None,
) -> dict:
    """Polish an ORE draft for readability and flow only (Issue #119 M2).

    Does not add new claims, urgency, or speculation. Does not reference
    events/signals outside allowed_framing_labels. Preserves meaning and
    respects tone_definition and sensitivity_level.

    Args:
        subject: Current draft subject line.
        message: Current draft message body.
        tone_definition: Playbook tone instruction (e.g. "Use only gentle framing").
        sensitivity_level: ESL sensitivity level (e.g. "low", "medium", "high").
        forbidden_phrases: Pack phrases that must not appear in output.
        allowed_framing_labels: Only these signal categories may be referenced.
        pack: Optional pack for pack-specific prompt (v2); else app prompt.

    Returns:
        Dict with "subject" and "message" (polished), or {"subject": "", "message": ""}
        on any failure (prompt render, LLM error, invalid JSON).
    """
    tone_instruction = _build_tone_instruction(tone_definition, sensitivity_level)
    forbidden_str = "\n".join(
        f"- {p}" for p in (forbidden_phrases or []) if p and isinstance(p, str)
    )
    allowed_str = ", ".join(
        str(label) for label in (allowed_framing_labels or []) if label is not None
    )

    try:
        prompt = resolve_prompt_content(
            "ore_polish_v1",
            pack,
            SUBJECT=subject or "",
            MESSAGE=message or "",
            TONE_INSTRUCTION=tone_instruction,
            FORBIDDEN_PHRASES=forbidden_str,
            ALLOWED_FRAMING=allowed_str,
        )
    except Exception:
        logger.exception("Failed to render ore_polish_v1 prompt")
        return _EMPTY_DRAFT.copy()

    try:
        llm = get_llm_provider(role=ModelRole.OUTREACH)
        raw = llm.complete(
            prompt,
            response_format={"type": "json_object"},
            temperature=0.3,
        )
    except Exception:
        logger.exception("ORE polish LLM call failed")
        return _EMPTY_DRAFT.copy()

    parsed = _parse_json_safe(raw)
    if parsed is None:
        logger.error("ORE polish LLM returned invalid JSON")
        return _EMPTY_DRAFT.copy()

    return {
        "subject": parsed.get("subject", ""),
        "message": parsed.get("message", ""),
    }
