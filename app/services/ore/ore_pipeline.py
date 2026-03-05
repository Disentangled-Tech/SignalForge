"""ORE pipeline — TRS → ESL → policy gate → draft → critic → persist (Issue #124, #106, #122).

All outreach behavior is pack-driven: pattern frame is chosen by dominant TRS dimension
(get_dominant_trs_dimension); channel, tone, and recipient label come from pack/playbook.
No hardcoded domain logic (e.g. no "Founder" unless pack taxonomy defines recipient_label).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Company, OutreachRecommendation, ReadinessSnapshot
from app.services.esl.engagement_snapshot_writer import compute_esl_from_context
from app.services.esl.esl_decision import CORE_BAN_SIGNAL_IDS
from app.services.esl.esl_engine import compute_outreach_score
from app.services.ore.critic import check_critic
from app.services.ore.dominant_dimension import get_dominant_trs_dimension
from app.services.ore.draft_generator import generate_ore_draft
from app.services.ore.playbook_loader import DEFAULT_PLAYBOOK_NAME, get_ore_playbook
from app.services.ore.policy_gate import PolicyGateResult, check_policy_gate
from app.services.ore.polisher import polish_ore_draft
from app.services.ore.strategy_selector import select_outreach_strategy
from app.services.pack_resolver import get_default_pack_id, get_pack_for_workspace, resolve_pack
from app.services.readiness.human_labels import event_type_to_label

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)

# M4: limit top signal labels passed to draft (framing only; no raw observation text)
_ORE_TOP_SIGNALS_LIMIT = 5


def _tone_definition_for_recommendation(playbook: dict, recommendation_type: str) -> str:
    """Resolve playbook tone to a string for draft (M5). Supports tone as string or dict per recommendation_type."""
    raw = playbook.get("tone")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict):
        return (raw.get(recommendation_type) or raw.get("default") or "").strip()
    return ""


def _build_explainability_context(
    snapshot: ReadinessSnapshot,
    pack: Pack | None,
    playbook: dict | None = None,
) -> tuple[str, list[str]]:
    """Build explainability snippet and top_signal_labels from ReadinessSnapshot.explain (M4).

    Uses only signal_id/category labels and safe framing text; no raw observation text.
    M5: When playbook provides explainability_snippet_template (non-empty string), use it
    with {{TOP_SIGNALS}} replaced by comma-separated labels; otherwise use built-in snippet.
    """
    explain = getattr(snapshot, "explain", None) or {}
    top_events = explain.get("top_events") or []
    labels: list[str] = []
    seen: set[str] = set()
    for ev in top_events[:_ORE_TOP_SIGNALS_LIMIT]:
        if not isinstance(ev, dict):
            continue
        etype = ev.get("event_type") or ""
        if etype and etype not in seen:
            seen.add(etype)
            labels.append(event_type_to_label(etype, pack=pack))
    top_signals_str = ", ".join(labels) if labels else ""
    template = (
        playbook.get("explainability_snippet_template").strip()
        if isinstance(playbook, dict)
        and isinstance(playbook.get("explainability_snippet_template"), str)
        and playbook.get("explainability_snippet_template", "").strip()
        else None
    )
    if template:
        snippet = template.replace("{{TOP_SIGNALS}}", top_signals_str) if labels else ""
    else:
        snippet = (
            "Top contributing categories: see TOP_SIGNALS below. Use for framing only; do not reference specific events."
            if labels
            else ""
        )
    return (snippet, labels)


def _no_reference_signal_ids(pack: "Pack") -> set[str]:  # noqa: UP037 — Pack is TYPE_CHECKING-only
    """Signal IDs that must not be referenced in ORE drafts (Issue #120 M3).

    Union of core bans, pack blocked_signals, and both sides of prohibited_combinations.
    """
    policy = getattr(pack, "esl_policy", None) or {}
    blocked = policy.get("blocked_signals") or []
    blocked_set = {str(s) for s in blocked} if isinstance(blocked, list) else set()
    prohibited = policy.get("prohibited_combinations") or []
    prohibited_flat: set[str] = set()
    if isinstance(prohibited, list):
        for pair in prohibited:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                prohibited_flat.add(str(pair[0]))
                prohibited_flat.add(str(pair[1]))
    return CORE_BAN_SIGNAL_IDS | blocked_set | prohibited_flat


def _resolve_ore_pack_id(
    db: Session,
    *,
    pack_id: UUID | None = None,
    workspace_id: str | None = None,
) -> UUID | None:
    """Resolve pack_id for ORE: explicit pack_id, else workspace, else default (Issue #122 M1)."""
    if pack_id is not None:
        return pack_id
    if workspace_id is not None:
        return get_pack_for_workspace(db, workspace_id)
    return get_default_pack_id(db)


def generate_ore_recommendation(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    pack_id: UUID | None = None,
    workspace_id: str | None = None,
    stability_modifier: float | None = None,
    cooldown_active: bool | None = None,
    alignment_high: bool | None = None,
    esl_decision: str | None = None,
    sensitivity_level: str | None = None,
) -> OutreachRecommendation | None:
    """Run full ORE pipeline: ESL suppress check → policy gate → draft → critic → persist.

    Pack-driven (Issue #121): pack/playbook supply pattern_frames, channel, tone; pattern
    frame is selected by dominant TRS dimension (get_dominant_trs_dimension). Recipient
    label comes from pack taxonomy (recipient_label) when present, else "Contact".

    Pack resolution (Issue #122 M1): when pack_id is None, uses get_pack_for_workspace(db,
    workspace_id) if workspace_id is set, else get_default_pack_id(db).

    When stability_modifier is None, computes ESL from context (ReadinessSnapshot,
    SignalEvents, OutreachHistory, Company) and uses ctx esl_decision/sensitivity_level.
    Pass explicit values for tests (including esl_decision/sensitivity_level when injecting).

    M4: If esl_decision == "suppress", no draft is generated (Observe Only). When playbook
    defines sensitivity_levels and entity sensitivity_level is not in the list, no draft
    and recommendation capped at Soft Value Share.

    Returns OutreachRecommendation or None if company/snapshot/pack not found.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None

    resolved_pack_id = _resolve_ore_pack_id(db, pack_id=pack_id, workspace_id=workspace_id)
    if resolved_pack_id is None:
        return None

    pack = resolve_pack(db, resolved_pack_id)
    if pack is None:
        return None
    playbook = get_ore_playbook(pack, playbook_name=DEFAULT_PLAYBOOK_NAME)

    snapshot = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of == as_of,
            ReadinessSnapshot.pack_id == resolved_pack_id,
        )
        .first()
    )
    if not snapshot:
        return None

    trs = snapshot.composite

    # M5: tone_constraint from ESL context when using computed ESL (for sensitivity gating in draft).
    tone_constraint_esl: str | None = None

    # Compute or use provided ESL (Issue #106)
    # ESL signal set: legacy (pack-scoped); not passing core_pack_id (Issue #287).
    if stability_modifier is not None:
        sm = stability_modifier
        esl_composite = sm
        cooldown = cooldown_active if cooldown_active is not None else False
        align = alignment_high if alignment_high is not None else True
        # Injected path: esl_decision/sensitivity_level from params (default None)
    else:
        ctx = compute_esl_from_context(db, company_id, as_of, pack_id=resolved_pack_id)
        if not ctx:
            return None
        sm = ctx["stability_modifier"]
        esl_composite = ctx["esl_composite"]
        cooldown = ctx["cadence_blocked"] if cooldown_active is None else cooldown_active
        align = ctx["alignment_high"] if alignment_high is None else alignment_high
        # Always use context values when using computed ESL; ignore any caller-provided esl_decision/sensitivity_level.
        esl_decision = ctx.get("esl_decision")
        sensitivity_level = ctx.get("sensitivity_level")
        # M5: pass ESL tone_constraint into draft so LLM respects sensitivity gating
        explain = ctx.get("explain") or {}
        tone_constraint_esl = (
            explain.get("tone_constraint")
            if isinstance(explain.get("tone_constraint"), str)
            else None
        )

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

    # M4: Playbook eligibility by sensitivity (case-insensitive per playbook schema).
    allowed_levels = (
        playbook.get("sensitivity_levels")
        if isinstance(playbook.get("sensitivity_levels"), list)
        else None
    )
    if allowed_levels:
        allowed_levels_normalized = {
            str(s).strip().lower() for s in allowed_levels if isinstance(s, str) and str(s).strip()
        }
    else:
        allowed_levels_normalized = set()
    if (
        gate.should_generate_draft
        and allowed_levels_normalized
        and sensitivity_level
        and isinstance(sensitivity_level, str)
        and sensitivity_level.strip().lower() not in allowed_levels_normalized
    ):
        gate = PolicyGateResult(
            recommendation_type="Soft Value Share",
            should_generate_draft=False,
            safeguards_triggered=(gate.safeguards_triggered or [])
            + ["Playbook excludes sensitivity level"],
        )

    # M1 (Issue #121): structured logging — pack_id, playbook_id, sensitivity_level, signals (no PII)
    explainability_snippet, top_signal_labels = _build_explainability_context(
        snapshot, pack, playbook
    )
    logger.info(
        "ORE recommendation: pack_id=%s playbook_id=%s sensitivity_level=%s recommendation_type=%s",
        resolved_pack_id,
        DEFAULT_PLAYBOOK_NAME,
        sensitivity_level,
        gate.recommendation_type,
        extra={
            "pack_id": str(resolved_pack_id),
            "playbook_id": DEFAULT_PLAYBOOK_NAME,
            "sensitivity_level": sensitivity_level,
            "recommendation_type": gate.recommendation_type,
            "signals": top_signal_labels,
        },
    )

    # Issue #117 M4: strategy from selector (channel, cta_type, value_asset, pattern_frame).
    dominant = get_dominant_trs_dimension(
        snapshot.momentum,
        snapshot.complexity,
        snapshot.pressure,
        snapshot.leadership_gap,
    )
    stability_cap_triggered = gate.recommendation_type == "Soft Value Share" and any(
        s and "Stability cap" in str(s) for s in (gate.safeguards_triggered or [])
    )
    strategy = select_outreach_strategy(
        recommendation_type=gate.recommendation_type,
        dominant_dimension=dominant,
        alignment_high=align,
        playbook=playbook,
        stability_cap_triggered=stability_cap_triggered,
    )
    strategy_notes_for_persist = {
        "channel": strategy.channel,
        "cta_type": strategy.cta_type,
        "value_asset": strategy.value_asset,
        "pattern_frame": strategy.pattern_frame,
    }

    draft_variants: list[dict] = []
    if gate.should_generate_draft:
        tone_def = _tone_definition_for_recommendation(playbook, gate.recommendation_type)
        draft = generate_ore_draft(
            company=company,
            recommendation_type=gate.recommendation_type,
            pattern_frame=strategy.pattern_frame,
            value_asset=strategy.value_asset,
            cta=strategy.cta_type,
            pack=pack,
            explainability_snippet=explainability_snippet,
            top_signal_labels=top_signal_labels,
            tone_constraint=tone_constraint_esl,
            tone_definition=tone_def or None,
        )

        # Optional polish (Issue #119): when enable_ore_polish is True, polish then run critic on polished draft
        candidate_draft = draft
        used_polish = False
        if playbook.get("enable_ore_polish") is True:
            polished = polish_ore_draft(
                draft.get("subject", ""),
                draft.get("message", ""),
                tone_definition=tone_def or None,
                sensitivity_level=sensitivity_level,
                forbidden_phrases=playbook.get("forbidden_phrases") or [],
                allowed_framing_labels=top_signal_labels,
                pack=pack,
            )
            if polished.get("subject") or polished.get("message"):
                candidate_draft = polished
                used_polish = True

        forbidden_phrases = playbook.get("forbidden_phrases") or []
        if candidate_draft.get("subject") or candidate_draft.get("message"):
            critic_result = check_critic(
                candidate_draft.get("subject", ""),
                candidate_draft.get("message", ""),
                forbidden_phrases=forbidden_phrases,
            )
            if critic_result.passed:
                draft_variants = [candidate_draft]
            else:
                # If we used polished draft and it failed critic, retry with original draft (Issue #119)
                if used_polish:
                    candidate_draft = draft
                    critic_result = check_critic(
                        draft.get("subject", ""),
                        draft.get("message", ""),
                        forbidden_phrases=forbidden_phrases,
                    )
                if critic_result.passed:
                    draft_variants = [candidate_draft]
                else:
                    # Use critic-compliant fallback when draft fails; retry with original if polish was used
                    fallback = _build_critic_compliant_fallback(
                        company=company,
                        value_asset=strategy.value_asset,
                        cta=strategy.cta_type,
                    )
                    fallback_critic = check_critic(
                        fallback.get("subject", ""),
                        fallback.get("message", ""),
                        forbidden_phrases=forbidden_phrases,
                    )
                    if fallback_critic.passed:
                        draft_variants = [fallback]
                    else:
                        # Mark for manual review — still store original draft (Issue #120 M3)
                        draft_variants = [draft]
                        strategy_notes_for_persist = {
                            **strategy_notes_for_persist,
                            "message": _strategy_notes_for_critic_failure(critic_result),
                        }
                        _log_critic_violations(
                            critic_result, company_id=company_id, pack_id=resolved_pack_id
                        )

    # Issue #115 M1: generation_version from pack manifest (Pack from loader always has manifest)
    generation_version = (pack.manifest.get("version") or "1")[:64]

    # Issue #117 M4: channel from strategy selector (playbook channels or default "LinkedIn DM")
    channel = strategy.channel

    # Issue #115 M2: upsert by (company_id, as_of, pack_id) — update existing or insert
    existing = (
        db.query(OutreachRecommendation)
        .filter(
            OutreachRecommendation.company_id == company_id,
            OutreachRecommendation.as_of == as_of,
            OutreachRecommendation.pack_id == resolved_pack_id,
        )
        .first()
    )
    if existing:
        existing.recommendation_type = gate.recommendation_type
        existing.outreach_score = outreach_score
        existing.channel = channel
        existing.draft_variants = draft_variants if draft_variants else None
        existing.strategy_notes = strategy_notes_for_persist
        existing.safeguards_triggered = gate.safeguards_triggered or None
        existing.generation_version = generation_version
        existing.playbook_id = DEFAULT_PLAYBOOK_NAME
        db.commit()
        db.refresh(existing)
        return existing

    rec = OutreachRecommendation(
        company_id=company_id,
        as_of=as_of,
        recommendation_type=gate.recommendation_type,
        outreach_score=outreach_score,
        channel=channel,
        draft_variants=draft_variants if draft_variants else None,
        strategy_notes=strategy_notes_for_persist,
        safeguards_triggered=gate.safeguards_triggered or None,
        generation_version=generation_version,
        pack_id=resolved_pack_id,
        playbook_id=DEFAULT_PLAYBOOK_NAME,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def get_or_create_ore_recommendation(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    pack_id: UUID | None = None,
    workspace_id: str | None = None,
) -> OutreachRecommendation | None:
    """Return existing ORE recommendation or run pipeline and return result (Issue #122 M1).

    Resolves pack via _resolve_ore_pack_id (pack_id else workspace_id else default).
    If an OutreachRecommendation exists for (company_id, as_of, resolved_pack_id), returns it.
    Otherwise runs generate_ore_recommendation and returns the new or updated row, or None.
    """
    resolved_pack_id = _resolve_ore_pack_id(db, pack_id=pack_id, workspace_id=workspace_id)
    if resolved_pack_id is None:
        return None
    existing = (
        db.query(OutreachRecommendation)
        .filter(
            OutreachRecommendation.company_id == company_id,
            OutreachRecommendation.as_of == as_of,
            OutreachRecommendation.pack_id == resolved_pack_id,
        )
        .first()
    )
    if existing is not None:
        return existing
    return generate_ore_recommendation(
        db,
        company_id=company_id,
        as_of=as_of,
        pack_id=resolved_pack_id,
        workspace_id=None,
    )


def regenerate_ore_draft(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    pack_id: UUID | None = None,
    workspace_id: str | None = None,
) -> OutreachRecommendation | None:
    """Regenerate ORE draft for an existing recommendation (Issue #123 M2).

    Loads the existing OutreachRecommendation by (company_id, as_of, resolved_pack_id),
    re-runs policy gate with current ESL context, and if the gate allows draft generation:
    generates a new draft (with critic), appends the current draft to draft_version_history,
    increments draft_generation_number, and updates draft_variants to the new draft.

    Returns the updated OutreachRecommendation, or None if no recommendation exists,
    pack/snapshot/context cannot be resolved, or the policy gate blocks draft generation
    (e.g. cooldown active or ESL suppress).

    TODO(Issue #123 M3): When exposing via POST .../regenerate, enforce authz so callers
    can only regenerate for companies (and optionally workspaces) they are allowed to access.
    """
    resolved_pack_id = _resolve_ore_pack_id(db, pack_id=pack_id, workspace_id=workspace_id)
    if resolved_pack_id is None:
        return None

    existing = (
        db.query(OutreachRecommendation)
        .filter(
            OutreachRecommendation.company_id == company_id,
            OutreachRecommendation.as_of == as_of,
            OutreachRecommendation.pack_id == resolved_pack_id,
        )
        .first()
    )
    if not existing:
        return None

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None

    pack = resolve_pack(db, resolved_pack_id)
    if pack is None:
        return None
    playbook = get_ore_playbook(pack, playbook_name=DEFAULT_PLAYBOOK_NAME)

    snapshot = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of == as_of,
            ReadinessSnapshot.pack_id == resolved_pack_id,
        )
        .first()
    )
    if not snapshot:
        return None

    ctx = compute_esl_from_context(db, company_id, as_of, pack_id=resolved_pack_id)
    if not ctx:
        return None

    sm = ctx["stability_modifier"]
    cooldown = ctx["cadence_blocked"]
    align = ctx["alignment_high"]
    esl_decision = ctx.get("esl_decision")
    sensitivity_level = ctx.get("sensitivity_level")
    tone_constraint_esl = None
    explain = ctx.get("explain") or {}
    if isinstance(explain.get("tone_constraint"), str):
        tone_constraint_esl = explain["tone_constraint"]

    if esl_decision == "suppress":
        return None

    gate = check_policy_gate(
        cooldown_active=cooldown,
        stability_modifier=sm,
        alignment_high=align,
        pack=pack,
    )

    allowed_levels = (
        playbook.get("sensitivity_levels")
        if isinstance(playbook.get("sensitivity_levels"), list)
        else None
    )
    if allowed_levels:
        allowed_levels_normalized = {
            str(s).strip().lower() for s in allowed_levels if isinstance(s, str) and str(s).strip()
        }
    else:
        allowed_levels_normalized = set()
    if (
        gate.should_generate_draft
        and allowed_levels_normalized
        and sensitivity_level
        and isinstance(sensitivity_level, str)
        and sensitivity_level.strip().lower() not in allowed_levels_normalized
    ):
        gate = PolicyGateResult(
            recommendation_type="Soft Value Share",
            should_generate_draft=False,
            safeguards_triggered=(gate.safeguards_triggered or [])
            + ["Playbook excludes sensitivity level"],
        )

    if not gate.should_generate_draft:
        return None

    explainability_snippet, top_signal_labels = _build_explainability_context(
        snapshot, pack, playbook
    )
    no_ref_signal_ids = _no_reference_signal_ids(pack)
    entity_signal_ids = ctx.get("signal_ids") or set()
    suppressed_signal_ids_for_critic = entity_signal_ids & no_ref_signal_ids

    # Issue #117 M4: strategy from selector (same as generate_ore_recommendation).
    dominant = get_dominant_trs_dimension(
        snapshot.momentum,
        snapshot.complexity,
        snapshot.pressure,
        snapshot.leadership_gap,
    )
    stability_cap_triggered = gate.recommendation_type == "Soft Value Share" and any(
        s and "Stability cap" in str(s) for s in (gate.safeguards_triggered or [])
    )
    strategy = select_outreach_strategy(
        recommendation_type=gate.recommendation_type,
        dominant_dimension=dominant,
        alignment_high=align,
        playbook=playbook,
        stability_cap_triggered=stability_cap_triggered,
    )
    tone_def = _tone_definition_for_recommendation(playbook, gate.recommendation_type)

    draft = generate_ore_draft(
        company=company,
        recommendation_type=gate.recommendation_type,
        pattern_frame=strategy.pattern_frame,
        value_asset=strategy.value_asset,
        cta=strategy.cta_type,
        pack=pack,
        explainability_snippet=explainability_snippet,
        top_signal_labels=top_signal_labels,
        tone_constraint=tone_constraint_esl,
        tone_definition=tone_def or None,
    )

    candidate_draft = draft
    used_polish = False
    if playbook.get("enable_ore_polish") is True:
        polished = polish_ore_draft(
            draft.get("subject", ""),
            draft.get("message", ""),
            tone_definition=tone_def or None,
            sensitivity_level=sensitivity_level,
            forbidden_phrases=playbook.get("forbidden_phrases") or [],
            allowed_framing_labels=top_signal_labels,
            pack=pack,
        )
        if polished.get("subject") or polished.get("message"):
            candidate_draft = polished
            used_polish = True

    forbidden_phrases = playbook.get("forbidden_phrases") or []
    critic_kwargs = {
        "forbidden_phrases": forbidden_phrases,
        "suppressed_signal_ids": suppressed_signal_ids_for_critic or None,
        "tone_constraint": tone_constraint_esl,
        "pack_id": resolved_pack_id,
        "allowed_signal_labels": top_signal_labels or None,
    }
    if not (candidate_draft.get("subject") or candidate_draft.get("message")):
        return None
    critic_result = check_critic(
        candidate_draft.get("subject", ""),
        candidate_draft.get("message", ""),
        **critic_kwargs,
    )
    if critic_result.passed:
        new_draft = candidate_draft
    else:
        if used_polish:
            candidate_draft = draft
            critic_result = check_critic(
                draft.get("subject", ""),
                draft.get("message", ""),
                **critic_kwargs,
            )
        if critic_result.passed:
            new_draft = candidate_draft
        else:
            fallback = _build_critic_compliant_fallback(
                company=company,
                value_asset=strategy.value_asset,
                cta=strategy.cta_type,
            )
            fallback_critic = check_critic(
                fallback.get("subject", ""),
                fallback.get("message", ""),
                **critic_kwargs,
            )
            if fallback_critic.passed:
                new_draft = fallback
            else:
                new_draft = draft
                _log_critic_violations(
                    critic_result, company_id=company_id, pack_id=resolved_pack_id
                )

    # Archive current draft to version history before replacing (Issue #123)
    current_variants = existing.draft_variants or []
    history = list(existing.draft_version_history or [])
    if current_variants:
        current_draft = current_variants[0]
        history.append(
            {
                "version": existing.draft_generation_number,
                "subject": current_draft.get("subject", ""),
                "message": current_draft.get("message", ""),
                "created_at_utc": datetime.now(UTC).isoformat(),
            }
        )

    existing.draft_version_history = history if history else None
    existing.draft_generation_number = existing.draft_generation_number + 1
    existing.draft_variants = [new_draft]
    db.commit()
    db.refresh(existing)
    return existing


def _log_critic_violations(
    critic_result: object,
    *,
    company_id: int,
    pack_id: UUID,
) -> None:
    """Log ORE critic violations for auditing (Issue #120 M3): violation_type, pack_id, signal_id."""
    from app.services.ore.critic import CriticResult

    if not isinstance(critic_result, CriticResult) or critic_result.passed:
        return
    details = critic_result.violation_details or []
    for v in details:
        # Critic uses "violation_type"; support legacy "type" for backward compat
        vtype = v.get("violation_type") or v.get("type") or "unknown"
        logger.warning(
            "ORE critic violation: type=%s pack_id=%s company_id=%s",
            vtype,
            pack_id,
            company_id,
            extra={
                "violation_type": vtype,
                "pack_id": str(pack_id),
                "signal_id": v.get("signal_id"),
                "company_id": company_id,
            },
        )
    if not details and critic_result.violations:
        logger.warning(
            "ORE critic violation: pack_id=%s company_id=%s violations=%s",
            pack_id,
            company_id,
            critic_result.violations,
            extra={"pack_id": str(pack_id), "company_id": company_id},
        )


def _strategy_notes_for_critic_failure(critic_result: object) -> str:
    """Build strategy_notes message when storing draft that failed critic (Issue #120 M3)."""
    from app.services.ore.critic import CriticResult

    if not isinstance(critic_result, CriticResult) or critic_result.passed:
        return "Manual Review: critic check"
    parts = [f"Manual Review: {v}" for v in (critic_result.violations or [])[:3]]
    if (critic_result.violations or [])[3:]:
        parts.append("...")
    return "; ".join(parts) if parts else "Manual Review: critic violations"


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
