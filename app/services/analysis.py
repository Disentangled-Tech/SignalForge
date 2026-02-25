"""Analysis pipeline — stage classification + pain signal detection."""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.llm.router import ModelRole, get_llm_provider

if TYPE_CHECKING:
    from app.packs.loader import Pack
from app.models.analysis_record import AnalysisRecord
from app.models.company import Company
from app.models.operator_profile import OperatorProfile
from app.models.signal_record import SignalRecord
from app.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

# The 6 allowed stage values from the prompt template.
ALLOWED_STAGES = frozenset(
    {
        "idea",
        "mvp_building",
        "early_customers",
        "scaling_team",
        "enterprise_transition",
        "struggling_execution",
    }
)

_DEFAULT_STAGE = "early_customers"

# Delimiter used when concatenating raw LLM responses for storage.
_RAW_RESPONSE_DELIMITER = "\n\n===== PAIN SIGNALS RESPONSE =====\n\n"


def _parse_json_safe(text: str) -> dict | None:
    """Try to parse *text* as JSON. Return ``None`` on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _call_llm_json(llm, prompt: str, *, temperature: float = 0.3) -> tuple[dict | None, str]:
    """Call the LLM expecting JSON, with one retry on parse failure.

    Returns (parsed_dict_or_None, raw_response_text).
    """
    raw = llm.complete(
        prompt,
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    parsed = _parse_json_safe(raw)
    if parsed is not None:
        return parsed, raw

    # Retry once with a simpler prompt.
    logger.warning("LLM returned invalid JSON, retrying with simplified prompt")
    retry_prompt = (
        "Your previous response was not valid JSON. "
        "Please return ONLY valid JSON with no extra text.\n\n"
        f"Original prompt:\n{prompt}"
    )
    raw_retry = llm.complete(
        retry_prompt,
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    parsed_retry = _parse_json_safe(raw_retry)
    if parsed_retry is not None:
        return parsed_retry, raw_retry

    logger.error("LLM returned invalid JSON after retry")
    return None, raw_retry


def analyze_company(
    db: Session,
    company_id: int,
    pack: Pack | None = None,
    pack_id: uuid.UUID | None = None,
) -> AnalysisRecord | None:
    """Run the full analysis pipeline for a single company.

    1. Load company and signals from DB.
    2. Stage classification via LLM.
    3. Pain signal detection via LLM.
    4. Generate explanation paragraph.
    5. Persist and return an ``AnalysisRecord``.

    Parameters
    ----------
    db : Session
        Active database session.
    company_id : int
        Company to analyze.
    pack : Pack | None
        Optional pack for prompt selection (Phase 1: accepted but unused;
        Phase 2: pack.get_stage_classification_prompt() etc.).

    Returns
    -------
    AnalysisRecord | None
        The analysis record, or None if company not found or has no signals.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        logger.warning("analyze_company: company %s not found", company_id)
        return None

    signals = (
        db.query(SignalRecord)
        .filter(SignalRecord.company_id == company_id)
        .all()
    )
    if not signals:
        logger.info("analyze_company: no signals for company %s", company_id)
        return None

    signals_text = "\n\n---\n\n".join(s.content_text for s in signals)

    # Load operator profile (first row, or empty string).
    op_profile = db.query(OperatorProfile).first()
    operator_profile_md = op_profile.content if op_profile and op_profile.content else ""

    llm = get_llm_provider(role=ModelRole.REASONING)

    # ── Stage classification ──────────────────────────────────────────
    stage_prompt = render_prompt(
        "stage_classification_v1",
        COMPANY_NAME=company.name,
        WEBSITE_URL=company.website_url or "",
        FOUNDER_NAME=company.founder_name or "",
        COMPANY_NOTES=company.notes or "",
        SIGNALS_TEXT=signals_text,
        OPERATOR_PROFILE_MARKDOWN=operator_profile_md,
    )
    stage_data, raw_stage = _call_llm_json(llm, stage_prompt, temperature=0.3)

    if stage_data is None:
        stage_data = {
            "stage": _DEFAULT_STAGE,
            "confidence": 0,
            "evidence_bullets": [],
            "assumptions": [],
        }

    stage = stage_data.get("stage", _DEFAULT_STAGE)
    if isinstance(stage, str):
        stage = stage.strip().lower()
    if not isinstance(stage, str) or stage not in ALLOWED_STAGES:
        logger.warning(
            "Invalid stage '%s' from LLM, defaulting to '%s'", stage, _DEFAULT_STAGE
        )
        stage = _DEFAULT_STAGE

    confidence = stage_data.get("confidence", 0)
    if not isinstance(confidence, int):
        try:
            confidence = int(confidence)
        except (ValueError, TypeError):
            confidence = 0
    confidence = max(0, min(100, confidence))

    evidence_bullets = stage_data.get("evidence_bullets", [])

    # ── Pain signal detection ─────────────────────────────────────────
    pain_prompt = render_prompt(
        "pain_signals_v1",
        COMPANY_NAME=company.name,
        WEBSITE_URL=company.website_url or "",
        FOUNDER_NAME=company.founder_name or "",
        COMPANY_NOTES=company.notes or "",
        SIGNALS_TEXT=signals_text,
    )
    pain_data, raw_pain = _call_llm_json(llm, pain_prompt, temperature=0.3)

    if pain_data is None:
        pain_data = {}

    # ── Explanation generation ────────────────────────────────────────
    evidence_text = "\n".join(f"- {b}" for b in evidence_bullets) if evidence_bullets else "(none)"
    pain_signals = pain_data.get("signals") or {}
    active_signals = {
        k: v for k, v in pain_signals.items()
        if isinstance(v, dict) and v.get("value")
    }
    pain_signals_summary = json.dumps(active_signals, indent=2) if active_signals else "(none)"
    top_risks = pain_data.get("top_risks") or []
    top_risks_text = ", ".join(str(x) for x in top_risks) if isinstance(top_risks, list) else str(top_risks)
    most_likely_next = pain_data.get("most_likely_next_problem") or ""

    explanation_prompt = render_prompt(
        "explanation_v1",
        COMPANY_NAME=company.name or "",
        STAGE=stage,
        EVIDENCE_BULLETS=evidence_text,
        PAIN_SIGNALS_SUMMARY=pain_signals_summary,
        TOP_RISKS=top_risks_text,
        MOST_LIKELY_NEXT_PROBLEM=most_likely_next,
    )
    explanation = llm.complete(explanation_prompt, temperature=0.7)

    # ── Persist AnalysisRecord ────────────────────────────────────────
    raw_llm_response = raw_stage + _RAW_RESPONSE_DELIMITER + raw_pain

    # Phase 2: Set pack_id when pack provided (for audit)
    resolved_pack_id: uuid.UUID | None = pack_id
    if resolved_pack_id is None and pack is not None:
        from app.services.pack_resolver import get_default_pack_id

        resolved_pack_id = get_default_pack_id(db)

    record = AnalysisRecord(
        company_id=company_id,
        source_type="full_analysis",
        stage=stage,
        stage_confidence=confidence,
        pain_signals_json=pain_data,
        evidence_bullets=evidence_bullets,
        explanation=explanation,
        raw_llm_response=raw_llm_response,
        pack_id=resolved_pack_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record

