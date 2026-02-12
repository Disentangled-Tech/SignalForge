"""Outreach message generator — personalised first-touch drafts."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.llm.router import get_llm_provider
from app.models.analysis_record import AnalysisRecord
from app.models.company import Company
from app.models.operator_profile import OperatorProfile
from app.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

_MAX_MESSAGE_WORDS = 140


def _parse_json_safe(text: str) -> dict | None:
    """Try to parse *text* as JSON.  Return ``None`` on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_pain_field(pain_signals: dict | None, key: str) -> str:
    """Safely pull a string field from the pain_signals_json dict."""
    if not isinstance(pain_signals, dict):
        return ""
    value = pain_signals.get(key, "")
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value) if value else ""


def generate_outreach(
    db: Session,
    company: Company,
    analysis: AnalysisRecord,
) -> dict:
    """Generate a personalised outreach draft for a company.

    Returns a dict with keys ``subject`` and ``message``.
    On any LLM failure returns ``{"subject": "", "message": ""}``.
    """
    empty = {"subject": "", "message": ""}

    # Load operator profile (first row, or empty string if none).
    try:
        op_profile = db.query(OperatorProfile).first()
    except Exception:
        logger.exception("Failed to load operator profile")
        op_profile = None
    operator_md = op_profile.content if op_profile and op_profile.content else ""

    pain = analysis.pain_signals_json or {}

    evidence_bullets = analysis.evidence_bullets or []
    evidence_text = "\n".join(f"- {b}" for b in evidence_bullets) if evidence_bullets else ""

    try:
        prompt = render_prompt(
            "outreach_v1",
            OPERATOR_PROFILE_MARKDOWN=operator_md,
            COMPANY_NAME=company.name or "",
            FOUNDER_NAME=company.founder_name or "",
            WEBSITE_URL=company.website_url or "",
            COMPANY_NOTES=company.notes or "",
            STAGE=analysis.stage or "",
            TOP_RISKS=_extract_pain_field(pain, "top_risks"),
            MOST_LIKELY_NEXT_PROBLEM=_extract_pain_field(pain, "most_likely_next_problem"),
            RECOMMENDED_CONVERSATION_ANGLE=_extract_pain_field(pain, "recommended_conversation_angle"),
            EVIDENCE_BULLETS=evidence_text,
        )
    except Exception:
        logger.exception("Failed to render outreach_v1 prompt")
        return empty

    try:
        llm = get_llm_provider()
        raw = llm.complete(
            prompt,
            response_format={"type": "json_object"},
            temperature=0.7,
        )
    except Exception:
        logger.exception("LLM call failed for outreach generation")
        return empty

    parsed = _parse_json_safe(raw)
    if parsed is None:
        logger.error("Outreach LLM returned invalid JSON")
        return empty

    subject = parsed.get("subject", "")
    message = parsed.get("message", "")

    # Word-count validation (warning only — keep the message).
    word_count = len(message.split())
    if word_count > _MAX_MESSAGE_WORDS:
        logger.warning(
            "Outreach message for %s is %d words (limit %d)",
            company.name,
            word_count,
            _MAX_MESSAGE_WORDS,
        )

    return {"subject": subject, "message": message}

