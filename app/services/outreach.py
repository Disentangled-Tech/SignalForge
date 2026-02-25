"""Outreach message generator — personalised first-touch drafts."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.packs.loader import Pack

from app.llm.router import ModelRole, get_llm_provider
from app.models.analysis_record import AnalysisRecord
from app.models.company import Company
from app.models.operator_profile import OperatorProfile
from app.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

_MAX_MESSAGE_WORDS = 140


def _validate_claims(
    claims: list[str], profile_content: str
) -> tuple[list[str], list[str]]:
    """Check which claims are actual substrings of the operator profile.

    Returns ``(valid_claims, invalid_claims)``.
    A claim is valid if it appears as a case-insensitive substring of
    *profile_content*.
    """
    if not profile_content:
        return ([], list(claims))
    lower_profile = profile_content.lower()
    valid: list[str] = []
    invalid: list[str] = []
    for claim in claims:
        if claim and claim.lower() in lower_profile:
            valid.append(claim)
        else:
            invalid.append(claim)
    return (valid, invalid)


def _parse_json_safe(text: str) -> dict | None:
    """Try to parse *text* as JSON.  Return ``None`` on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _truncate_to_word_limit(text: str, max_words: int) -> str:
    """Truncate text to max_words, preferring sentence boundaries."""
    words = text.split()
    if len(words) <= max_words:
        return text
    truncated = " ".join(words[:max_words])
    # Prefer sentence boundary: find last . ! ? in truncated
    last_boundary = max(
        truncated.rfind(". "),
        truncated.rfind("! "),
        truncated.rfind("? "),
    )
    if last_boundary >= 0:
        return truncated[: last_boundary + 1].rstrip()
    return truncated


# Patterns suggesting operator/experience claims (issue #31 Phase 3)
# Conservative to avoid false positives (e.g. "I've noticed" is fine)
_SUSPICIOUS_CLAIM_PATTERNS = [
    re.compile(r"\d+\s*years?\s+of\s+(experience|expertise)", re.I),
    re.compile(r"helped\s+\d+", re.I),
    re.compile(r"I've\s+(built|scaled|raised|led)\s+", re.I),
    re.compile(r"raised\s+\$", re.I),
    re.compile(r"\d+\s+(companies|startups)\b", re.I),
    re.compile(r"decades?\s+of", re.I),
    re.compile(r"\b(certified|certification)\b", re.I),
]


def _message_has_suspicious_claims(text: str) -> bool:
    """Return True if message contains phrases suggesting unbacked operator claims."""
    if not text or not isinstance(text, str):
        return False
    lower = text.lower()
    return any(p.search(lower) for p in _SUSPICIOUS_CLAIM_PATTERNS)


def _extract_pain_field(pain_signals: dict | None, key: str) -> str:
    """Safely pull a string field from the pain_signals_json dict."""
    if not isinstance(pain_signals, dict):
        return ""
    value = pain_signals.get(key, "")
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value) if value else ""


def _build_safe_fallback(
    company: Company,
    analysis: AnalysisRecord,
) -> dict:
    """Build a minimal outreach with no operator claims (issue #31).

    Used when hallucination guardrail cannot produce a verified message.
    References only company context: name, founder, evidence.
    """
    founder = (company.founder_name or "").strip() or "there"
    company_name = (company.name or "").strip() or "your company"
    evidence_bullets = analysis.evidence_bullets or []
    hook = (
        evidence_bullets[0]
        if evidence_bullets and isinstance(evidence_bullets[0], str)
        else "your recent activity"
    )
    subject = f"Quick question about {company_name}"
    message = (
        f"Hi {founder},\n\n"
        f"I noticed {hook}. "
        "Would you be open to a brief conversation?"
    )
    return {"subject": subject, "message": message}


def generate_outreach(
    db: Session,
    company: Company,
    analysis: AnalysisRecord,
    pack: Pack | None = None,
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

    # Empty profile: append instruction to forbid operator claims (issue #31)
    empty_profile_suffix = ""
    if not operator_md.strip():
        empty_profile_suffix = (
            "\n\nIMPORTANT: The operator profile is empty. Do NOT make any claims "
            "about the operator, experience, or credentials. Reference only company "
            "context (evidence, stage, notes). operator_claims_used must be []."
        )

    # Phase 2: offer_type from pack manifest for domain language.
    # When pack provided (e.g. from briefing with workspace context), use it.
    # Fallback "fractional CTO" preserves backward compat when pack unavailable.
    offer_type = "fractional CTO"
    try:
        if pack is None:
            from app.services.pack_resolver import get_default_pack

            pack = get_default_pack(db)
        if pack is not None and isinstance(pack.manifest, dict):
            offer_type = pack.manifest.get("offer_type", offer_type)
    except Exception:
        pass

    try:
        prompt = render_prompt(
            "outreach_v1",
            OFFER_TYPE=offer_type,
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
        prompt = prompt + empty_profile_suffix
    except Exception:
        logger.exception("Failed to render outreach_v1 prompt")
        return empty

    try:
        llm = get_llm_provider(role=ModelRole.OUTREACH)
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
    claims = parsed.get("operator_claims_used", [])

    # ── Hallucination guardrail ──────────────────────────────────────
    # Empty profile + any claims: invalid (issue #31)
    if claims and not operator_md.strip():
        logger.warning(
            "Empty profile but LLM returned claims for %s: %s — using safe fallback",
            company.name,
            claims,
        )
        return _build_safe_fallback(company, analysis)

    if claims and operator_md:
        valid, invalid = _validate_claims(claims, operator_md)
        if invalid:
            logger.warning(
                "Hallucinated claims for %s: %s",
                company.name,
                invalid,
            )
            # Retry once with amended prompt
            retry_suffix = (
                "\n\nIMPORTANT: The following claims were NOT found in the "
                "operator profile and must not be used: "
                + ", ".join(invalid)
                + ". Only use claims that are exact quotes from the profile."
            )
            try:
                retry_raw = llm.complete(
                    prompt + retry_suffix,
                    response_format={"type": "json_object"},
                    temperature=0.7,
                )
                retry_parsed = _parse_json_safe(retry_raw)
                if retry_parsed is not None:
                    retry_claims = retry_parsed.get("operator_claims_used", [])
                    retry_valid, retry_invalid = _validate_claims(
                        retry_claims, operator_md
                    )
                    if not retry_invalid:
                        # Retry succeeded — use retry result
                        subject = retry_parsed.get("subject", "")
                        message = retry_parsed.get("message", "")
                        claims = retry_claims
                    else:
                        logger.warning(
                            "Retry still has hallucinated claims for %s: %s — using safe fallback",
                            company.name,
                            retry_invalid,
                        )
                        return _build_safe_fallback(company, analysis)
            except Exception:
                logger.exception("LLM retry failed for outreach hallucination check")
                return _build_safe_fallback(company, analysis)

    # ── Phase 3: Message has claim-like phrases but operator_claims_used empty ──
    if (
        operator_md.strip()
        and not claims
        and _message_has_suspicious_claims(message)
    ):
        logger.warning(
            "Message for %s has suspicious claim phrases but operator_claims_used empty — retrying",
            company.name,
        )
        retry_suffix = (
            "\n\nIMPORTANT: The previous message may contain operator/experience/credential "
            "claims. Rewrite with NO such claims. Reference ONLY company context "
            "(evidence, stage, notes). operator_claims_used must be []."
        )
        try:
            retry_raw = llm.complete(
                prompt + retry_suffix,
                response_format={"type": "json_object"},
                temperature=0.5,
            )
            retry_parsed = _parse_json_safe(retry_raw)
            if retry_parsed is not None:
                retry_message = retry_parsed.get("message", "")
                retry_claims = retry_parsed.get("operator_claims_used", [])
                if not _message_has_suspicious_claims(retry_message):
                    if not retry_claims:
                        subject = retry_parsed.get("subject", subject)
                        message = retry_message
                    else:
                        retry_valid, retry_invalid = _validate_claims(
                            retry_claims, operator_md
                        )
                        if not retry_invalid:
                            subject = retry_parsed.get("subject", subject)
                            message = retry_message
                        else:
                            logger.warning(
                                "Retry has unbacked claims for %s: %s — using safe fallback",
                                company.name,
                                retry_invalid,
                            )
                            return _build_safe_fallback(company, analysis)
                else:
                    logger.warning(
                        "Retry still has suspicious claims for %s — using safe fallback",
                        company.name,
                    )
                    return _build_safe_fallback(company, analysis)
            else:
                return _build_safe_fallback(company, analysis)
        except Exception:
            logger.exception("LLM retry failed for suspicious-claims check")
            return _build_safe_fallback(company, analysis)

    # ── Word-count enforcement (PRD: shorten once on violation) ─────
    word_count = len(message.split())
    if word_count > _MAX_MESSAGE_WORDS:
        logger.warning(
            "Outreach message for %s is %d words (limit %d), shortening once",
            company.name,
            word_count,
            _MAX_MESSAGE_WORDS,
        )
        # Include the actual message so the LLM shortens THIS message, not regenerate
        # (regeneration could reintroduce hallucinated claims from earlier retry)
        shorten_prompt = (
            "Shorten the outreach message below to under 140 words. "
            "Preserve key points, tone, and personalization. Do NOT add new claims or content.\n\n"
            f"Current subject: {subject}\n\n"
            "Message to shorten:\n"
            "---BEGIN MESSAGE---\n"
            f"{message}\n"
            "---END MESSAGE---\n\n"
            "Return ONLY valid JSON: {\"subject\": \"...\", \"message\": \"...\"}"
        )
        try:
            retry_raw = llm.complete(
                shorten_prompt,
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            retry_parsed = _parse_json_safe(retry_raw)
            if retry_parsed is not None:
                retry_message = retry_parsed.get("message", "")
                retry_count = len(retry_message.split())
                if retry_count <= _MAX_MESSAGE_WORDS:
                    message = retry_message
                    subject = retry_parsed.get("subject", subject)
                else:
                    logger.info(
                        "Shorten attempt for %s still %d words, truncating",
                        company.name,
                        retry_count,
                    )
                    message = _truncate_to_word_limit(retry_message, _MAX_MESSAGE_WORDS)
            else:
                logger.warning(
                    "Shorten response invalid JSON for %s, truncating",
                    company.name,
                )
                message = _truncate_to_word_limit(message, _MAX_MESSAGE_WORDS)
        except Exception:
            logger.exception("Shorten attempt failed for %s, truncating", company.name)
            message = _truncate_to_word_limit(message, _MAX_MESSAGE_WORDS)

    return {"subject": subject, "message": message}

