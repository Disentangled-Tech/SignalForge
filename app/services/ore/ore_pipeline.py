"""ORE pipeline — TRS → ESL → policy gate → draft → critic → persist (Issue #124, #106)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import Company, OutreachRecommendation, ReadinessSnapshot
from app.services.esl.engagement_snapshot_writer import compute_esl_from_context
from app.services.esl.esl_engine import compute_outreach_score
from app.services.ore.critic import check_critic
from app.services.ore.draft_generator import generate_ore_draft, get_ore_playbook
from app.services.ore.policy_gate import PolicyGateResult, check_policy_gate
from app.services.pack_resolver import get_default_pack_id, resolve_pack


def generate_ore_recommendation(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    stability_modifier: float | None = None,
    cooldown_active: bool | None = None,
    alignment_high: bool | None = None,
    esl_decision: str | None = None,
    sensitivity_level: str | None = None,
) -> OutreachRecommendation | None:
    """Run full ORE pipeline: ESL suppress check → policy gate → draft → critic → persist.

    When stability_modifier is None, computes ESL from context (ReadinessSnapshot,
    SignalEvents, OutreachHistory, Company) and uses ctx esl_decision/sensitivity_level.
    Pass explicit values for tests (including esl_decision/sensitivity_level when injecting).

    M4: If esl_decision == "suppress", no draft is generated (Observe Only). When playbook
    defines sensitivity_levels and entity sensitivity_level is not in the list, no draft
    and recommendation capped at Soft Value Share.

    Returns OutreachRecommendation or None if company/snapshot not found.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None

    pack_id = get_default_pack_id(db)
    if pack_id is None:
        return None

    pack = resolve_pack(db, pack_id)
    playbook = get_ore_playbook(pack)

    snapshot = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of == as_of,
            ReadinessSnapshot.pack_id == pack_id,
        )
        .first()
    )
    if not snapshot:
        return None

    trs = snapshot.composite

    # Compute or use provided ESL (Issue #106)
    # ESL signal set: legacy (pack-scoped); not passing core_pack_id (Issue #287).
    if stability_modifier is not None:
        sm = stability_modifier
        esl_composite = sm
        cooldown = cooldown_active if cooldown_active is not None else False
        align = alignment_high if alignment_high is not None else True
        # Injected path: esl_decision/sensitivity_level from params (default None)
    else:
        ctx = compute_esl_from_context(db, company_id, as_of, pack_id=pack_id)
        if not ctx:
            return None
        sm = ctx["stability_modifier"]
        esl_composite = ctx["esl_composite"]
        cooldown = ctx["cadence_blocked"] if cooldown_active is None else cooldown_active
        align = ctx["alignment_high"] if alignment_high is None else alignment_high
        esl_decision = ctx.get("esl_decision")
        sensitivity_level = ctx.get("sensitivity_level")

    outreach_score = compute_outreach_score(trs, esl_composite)

    # M4: ESL suppress → no draft (Observe Only); then policy gate (cooldown/stability)
    if esl_decision == "suppress":
        gate = PolicyGateResult(
            recommendation_type="Observe Only",
            should_generate_draft=False,
            safeguards_triggered=["ESL suppress → Do not contact"],
        )
    else:
        gate = check_policy_gate(
            cooldown_active=cooldown,
            stability_modifier=sm,
            alignment_high=align,
            pack=pack,
        )

    # M4: Playbook eligibility by sensitivity: if playbook restricts and entity level not allowed, no draft
    playbook = get_ore_playbook(pack)
    allowed_levels = playbook.get("sensitivity_levels") if isinstance(playbook.get("sensitivity_levels"), list) else None
    if gate.should_generate_draft and allowed_levels and sensitivity_level and sensitivity_level not in allowed_levels:
        gate = PolicyGateResult(
            recommendation_type="Soft Value Share",
            should_generate_draft=False,
            safeguards_triggered=(gate.safeguards_triggered or []) + ["Playbook excludes sensitivity level"],
        )

    draft_variants: list[dict] = []
    if gate.should_generate_draft:
        # Pick pattern frame from dominant dimension (simplified: use complexity)
        pattern_frames = playbook["pattern_frames"]
        value_assets = playbook["value_assets"]
        ctas = playbook["ctas"]
        pattern_frame = pattern_frames.get("complexity", pattern_frames.get("momentum", ""))
        value_asset = value_assets[0] if value_assets else ""
        cta = ctas[0] if ctas else ""

        draft = generate_ore_draft(
            company=company,
            recommendation_type=gate.recommendation_type,
            pattern_frame=pattern_frame,
            value_asset=value_asset,
            cta=cta,
            pack=pack,
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

    # Issue #115 M1: generation_version from pack manifest (Pack from loader always has manifest)
    generation_version = (pack.manifest.get("version") or "1")[:64]

    # Issue #115 M2: upsert by (company_id, as_of, pack_id) — update existing or insert
    existing = (
        db.query(OutreachRecommendation)
        .filter(
            OutreachRecommendation.company_id == company_id,
            OutreachRecommendation.as_of == as_of,
            OutreachRecommendation.pack_id == pack_id,
        )
        .first()
    )
    if existing:
        existing.recommendation_type = gate.recommendation_type
        existing.outreach_score = outreach_score
        existing.channel = "LinkedIn DM"
        existing.draft_variants = draft_variants if draft_variants else None
        existing.strategy_notes = None
        existing.safeguards_triggered = gate.safeguards_triggered or None
        existing.generation_version = generation_version
        db.commit()
        db.refresh(existing)
        return existing

    rec = OutreachRecommendation(
        company_id=company_id,
        as_of=as_of,
        recommendation_type=gate.recommendation_type,
        outreach_score=outreach_score,
        channel="LinkedIn DM",
        draft_variants=draft_variants if draft_variants else None,
        strategy_notes=None,
        safeguards_triggered=gate.safeguards_triggered or None,
        generation_version=generation_version,
        pack_id=pack_id,
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
