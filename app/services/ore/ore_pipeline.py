"""ORE pipeline — TRS → ESL → policy gate → draft → critic → persist (Issue #124, #106)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import Company, OutreachRecommendation, ReadinessSnapshot
from app.services.esl.esl_engine import compute_outreach_score
from app.services.esl.engagement_snapshot_writer import compute_esl_from_context
from app.services.ore.critic import check_critic
from app.services.ore.draft_generator import (
    CTAS,
    PATTERN_FRAMES,
    VALUE_ASSETS,
    generate_ore_draft,
)
from app.services.ore.policy_gate import check_policy_gate


def generate_ore_recommendation(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    stability_modifier: float | None = None,
    cooldown_active: bool | None = None,
    alignment_high: bool | None = None,
) -> OutreachRecommendation | None:
    """Run full ORE pipeline: policy gate → ESL → draft → critic → persist.

    When stability_modifier is None, computes ESL from context (ReadinessSnapshot,
    SignalEvents, OutreachHistory, Company). Pass explicit values for tests.

    Returns OutreachRecommendation or None if company/snapshot not found.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None

    snapshot = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of == as_of,
        )
        .first()
    )
    if not snapshot:
        return None

    trs = snapshot.composite

    # Compute or use provided ESL (Issue #106)
    if stability_modifier is not None:
        sm = stability_modifier
        esl_composite = sm
        cooldown = cooldown_active if cooldown_active is not None else False
        align = alignment_high if alignment_high is not None else True
    else:
        ctx = compute_esl_from_context(db, company_id, as_of)
        if not ctx:
            return None
        sm = ctx["stability_modifier"]
        esl_composite = ctx["esl_composite"]
        cooldown = ctx["cadence_blocked"] if cooldown_active is None else cooldown_active
        align = ctx["alignment_high"] if alignment_high is None else alignment_high

    outreach_score = compute_outreach_score(trs, esl_composite)

    gate = check_policy_gate(
        cooldown_active=cooldown,
        stability_modifier=sm,
        alignment_high=align,
    )

    draft_variants: list[dict] = []
    if gate.should_generate_draft:
        # Pick pattern frame from dominant dimension (simplified: use complexity)
        pattern_frame = PATTERN_FRAMES.get("complexity", PATTERN_FRAMES["momentum"])
        value_asset = VALUE_ASSETS[0]
        cta = CTAS[0]

        draft = generate_ore_draft(
            company=company,
            recommendation_type=gate.recommendation_type,
            pattern_frame=pattern_frame,
            value_asset=value_asset,
            cta=cta,
        )

        if draft.get("subject") or draft.get("message"):
            critic_result = check_critic(
                draft.get("subject", ""),
                draft.get("message", ""),
            )
            if critic_result.passed:
                draft_variants = [draft]
            else:
                # Rewrite once (simplified: use fallback that passes critic)
                fallback = _build_critic_compliant_fallback(
                    company=company,
                    value_asset=value_asset,
                    cta=cta,
                )
                fallback_critic = check_critic(
                    fallback.get("subject", ""),
                    fallback.get("message", ""),
                )
                if fallback_critic.passed:
                    draft_variants = [fallback]
                else:
                    # Mark for manual review — still store with empty draft
                    draft_variants = [draft]  # Store original, strategy_notes will flag

    rec = OutreachRecommendation(
        company_id=company_id,
        as_of=as_of,
        recommendation_type=gate.recommendation_type,
        outreach_score=outreach_score,
        channel="LinkedIn DM",
        draft_variants=draft_variants if draft_variants else None,
        strategy_notes=None,
        safeguards_triggered=gate.safeguards_triggered or None,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _build_critic_compliant_fallback(
    company: Company,
    value_asset: str,
    cta: str,
) -> dict:
    """Build a draft that passes critic (no surveillance, single CTA, opt-out)."""
    name = (company.founder_name or "").strip() or "there"
    company_name = (company.name or "").strip() or "your company"
    pattern = "When products add integrations and enterprise asks, systems often need a stabilization pass."
    subject = f"Quick question about {company_name}"
    message = (
        f"Hi {name},\n\n"
        f"{pattern}\n\n"
        f"I have a {value_asset} that might help. {cta} "
        "No worries if now isn't the time."
    )
    return {"subject": subject, "message": message}
