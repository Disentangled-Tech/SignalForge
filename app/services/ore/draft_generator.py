"""ORE draft generator — produces ORE-compliant drafts (no evidence/surveillance)."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from app.llm.router import ModelRole, get_llm_provider
from app.models.company import Company
from app.prompts.loader import resolve_prompt_content

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)

# Pattern frames (generic, non-invasive) per ORE design spec §6
# Fallback when pack not provided or playbook missing (Phase 2, Step 3.5)
PATTERN_FRAMES = {
    "momentum": "When a team's pace picks up, tech decisions that worked earlier can start costing more.",
    "complexity": "When products add integrations/AI/enterprise asks, systems often need a stabilization pass.",
    "pressure": "When timelines get tighter, it helps to reduce decision load and get a clean plan.",
    "leadership_gap": "When there isn't a dedicated technical owner yet, teams often benefit from a short-term systems guide.",
}

VALUE_ASSETS = [
    "2-page Tech Inflection Checklist",
    "30-minute 'what's breaking next' map",
    "5 questions to reduce tech chaos",
]

CTAS = [
    "Want me to send that checklist?",
    "Open to a 15-min compare-notes call?",
    "If helpful, I can share a one-page approach—want it?",
]


def get_ore_playbook(pack: Pack | None) -> dict[str, Any]:
    """Return ORE playbook values: pattern_frames, value_assets, ctas (Phase 2, Step 3.5).

    When pack is provided and has ore_outreach playbook, use pack values;
    otherwise fall back to module constants.
    """
    if pack is None:
        return {
            "pattern_frames": PATTERN_FRAMES,
            "value_assets": VALUE_ASSETS,
            "ctas": CTAS,
        }
    playbook = pack.playbooks.get("ore_outreach") or {}
    return {
        "pattern_frames": playbook.get("pattern_frames") or PATTERN_FRAMES,
        "value_assets": playbook.get("value_assets") or VALUE_ASSETS,
        "ctas": playbook.get("ctas") or CTAS,
    }


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
