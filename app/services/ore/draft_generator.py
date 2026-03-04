"""ORE draft generator — produces ORE-compliant drafts (no evidence/surveillance)."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from app.llm.router import ModelRole, get_llm_provider
from app.models.company import Company
from app.prompts.loader import resolve_prompt_content
from app.services.ore.playbook_loader import (
    CTAS,
    PATTERN_FRAMES,
    VALUE_ASSETS,
    get_ore_playbook,
)

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (test_pack_fractional_cto_parity, etc.)
__all__ = ["PATTERN_FRAMES", "VALUE_ASSETS", "CTAS", "get_ore_playbook", "generate_ore_draft"]


def _parse_json_safe(text: str) -> dict | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def generate_ore_draft(
    company: Company,
    recommendation_type: str,
    pattern_frame: str,
    value_asset: str,
    cta: str,
    pack: Pack | None = None,
) -> dict:
    """Generate ORE-compliant draft (no evidence, no surveillance).

    Returns dict with subject, message. On failure returns empty strings.
    When pack is provided (e.g. from ORE pipeline), uses resolve_prompt_content for M4.
    """
    name = (company.founder_name or "").strip() or "there"
    company_name = (company.name or "").strip() or "your company"

    try:
        prompt = resolve_prompt_content(
            "ore_outreach_v1",
            pack,
            NAME=name,
            COMPANY=company_name,
            PATTERN_FRAME=pattern_frame,
            VALUE_ASSET=value_asset,
            CTA=cta,
        )
    except Exception:
        logger.exception("Failed to render ore_outreach_v1 prompt")
        return {"subject": "", "message": ""}

    try:
        llm = get_llm_provider(role=ModelRole.OUTREACH)
        raw = llm.complete(
            prompt,
            response_format={"type": "json_object"},
            temperature=0.5,
        )
    except Exception:
        logger.exception("ORE draft LLM call failed")
        return {"subject": "", "message": ""}

    parsed = _parse_json_safe(raw)
    if parsed is None:
        logger.error("ORE draft LLM returned invalid JSON")
        return {"subject": "", "message": ""}

    return {
        "subject": parsed.get("subject", ""),
        "message": parsed.get("message", ""),
    }
