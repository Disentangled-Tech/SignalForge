"""Write EngagementSnapshot to DB (Issue #106).

Computes ESL from ReadinessSnapshot, SignalEvents, OutreachHistory, Company.
Runs after readiness scoring; requires ReadinessSnapshot for company/as_of.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    Company,
    EngagementSnapshot,
    OutreachHistory,
    ReadinessSnapshot,
    SignalEvent,
    SignalInstance,
)
from app.services.esl.esl_constants import STABILITY_CAP_THRESHOLD
from app.services.esl.esl_decision import evaluate_esl_decision
from app.services.esl.esl_engine import (
    build_esl_explain,
    compute_alignment_modifier,
    compute_base_engageability,
    compute_cadence_modifier,
    compute_csi,
    compute_esl_composite,
    compute_outreach_score,
    compute_spi,
    compute_stability_modifier,
    compute_svi,
    map_esl_to_recommendation,
)
from app.services.pack_resolver import get_default_pack_id, resolve_pack


def _get_signal_ids_for_company(
    db: Session, company_id: int, pack_id: str | UUID | None
) -> set[str]:
    """Fetch signal_ids for company from SignalInstance (Issue #175).

    Returns empty set when no SignalInstances (e.g. watchlist company).
    """
    if pack_id is None:
        return set()
    instances = (
        db.query(SignalInstance.signal_id)
        .filter(
            SignalInstance.entity_id == company_id,
            SignalInstance.pack_id == pack_id,
        )
        .distinct()
        .all()
    )
    return {row[0] for row in instances if row[0]}


def compute_esl_from_context(
    db: Session,
    company_id: int,
    as_of: date,
    pack_id=None,
) -> dict[str, Any] | None:
    """Compute ESL from DB context without persisting (Issue #106).

    Returns dict with esl_composite, stability_modifier, recommendation_type,
    explain, cadence_blocked, alignment_high. Returns None if no ReadinessSnapshot.
    """
    pack_id = pack_id or get_default_pack_id(db)
    if pack_id is None:
        return None

    pack = resolve_pack(db, pack_id)

    # Treat pack_id IS NULL as default pack until backfill completes (Issue #189)
    pack_filter = or_(
        ReadinessSnapshot.pack_id == pack_id,
        ReadinessSnapshot.pack_id.is_(None),
    )
    readiness = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of == as_of,
            pack_filter,
        )
        .first()
    )
    if not readiness:
        return None

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None

    cutoff_dt = datetime.combine(as_of - timedelta(days=365), datetime.min.time()).replace(
        tzinfo=UTC
    )
    # Pack-scoped: only use events for this pack or legacy NULL (Issue #189)
    event_pack_filter = or_(
        SignalEvent.pack_id == pack_id,
        SignalEvent.pack_id.is_(None),
    )
    events = (
        db.query(SignalEvent)
        .filter(
            SignalEvent.company_id == company_id,
            SignalEvent.event_time >= cutoff_dt,
            event_pack_filter,
        )
        .order_by(SignalEvent.event_time.asc())
        .all()
    )

    spi_cutoff = as_of - timedelta(days=90)
    pressure_snapshots = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of >= spi_cutoff,
            ReadinessSnapshot.as_of <= as_of,
            pack_filter,
        )
        .order_by(ReadinessSnapshot.as_of.asc())
        .all()
    )

    last_outreach = (
        db.query(OutreachHistory.sent_at)
        .filter(OutreachHistory.company_id == company_id)
        .order_by(OutreachHistory.sent_at.desc())
        .limit(1)
        .scalar()
    )

    be = compute_base_engageability(readiness.composite)
    svi = compute_svi(events, as_of, pack=pack)
    spi = compute_spi(pressure_snapshots, as_of)
    csi = compute_csi(events, as_of)
    sm = compute_stability_modifier(svi, spi, csi)
    cm = compute_cadence_modifier(last_outreach, as_of)
    am = compute_alignment_modifier(company.alignment_ok_to_contact)
    esl_composite = compute_esl_composite(be, sm, cm, am)
    recommendation_type = map_esl_to_recommendation(esl_composite, pack=pack)

    stability_cap_triggered = sm < STABILITY_CAP_THRESHOLD
    cadence_blocked = cm == 0.0
    # Stability cap must not override cadence-blocked: Observe Only takes precedence.
    if stability_cap_triggered and not cadence_blocked:
        recommendation_type = "Soft Value Share"
        logger = logging.getLogger(__name__)
        logger.info(
            "Stability cap triggered: company_id=%s, stability_modifier=%.2f",
            company_id,
            sm,
        )

    explain = build_esl_explain(
        base_engageability=be,
        stability_modifier=sm,
        cadence_modifier=cm,
        alignment_modifier=am,
        svi=svi,
        spi=spi,
        csi=csi,
        esl_composite=esl_composite,
        recommendation_type=recommendation_type,
        cadence_blocked=cadence_blocked,
        stability_cap_triggered=stability_cap_triggered,
    )

    # Issue #175: ESL decision gate (Phase 2); Phase 4: also in dedicated columns
    signal_ids = _get_signal_ids_for_company(db, company_id, pack_id)
    esl_result = evaluate_esl_decision(signal_ids, pack)
    explain["esl_decision"] = esl_result.decision
    explain["esl_reason_code"] = esl_result.reason_code
    explain["sensitivity_level"] = esl_result.sensitivity_level
    explain["tone_constraint"] = esl_result.tone_constraint

    return {
        "esl_composite": esl_composite,
        "stability_modifier": sm,
        "recommendation_type": recommendation_type,
        "explain": explain,
        "cadence_blocked": cadence_blocked,
        "alignment_high": company.alignment_ok_to_contact is not False,
        "trs": readiness.composite,
        "pack_id": pack_id,
        "esl_decision": esl_result.decision,
        "esl_reason_code": esl_result.reason_code,
        "sensitivity_level": esl_result.sensitivity_level,
    }


def write_engagement_snapshot(
    db: Session,
    company_id: int,
    as_of: date,
    pack_id=None,
) -> EngagementSnapshot | None:
    """Compute ESL from context and persist EngagementSnapshot (Issue #189).

    Requires ReadinessSnapshot for company/as_of/pack_id. Fetches SignalEvents (365d),
    OutreachHistory (last sent), Company alignment. Upserts EngagementSnapshot.
    """
    ctx = compute_esl_from_context(db, company_id, as_of, pack_id=pack_id)
    if not ctx:
        return None

    esl_composite = ctx["esl_composite"]
    recommendation_type = ctx["recommendation_type"]
    explain = ctx["explain"]
    svi = explain["svi"]
    spi = explain["spi"]
    csi = explain["csi"]
    trs = ctx["trs"]
    outreach_score = compute_outreach_score(trs, esl_composite)

    cadence_blocked = ctx["cadence_blocked"]
    pack_id = ctx["pack_id"]
    esl_decision = ctx.get("esl_decision")
    esl_reason_code = ctx.get("esl_reason_code")
    sensitivity_level = ctx.get("sensitivity_level")

    existing = (
        db.query(EngagementSnapshot)
        .filter(
            EngagementSnapshot.company_id == company_id,
            EngagementSnapshot.as_of == as_of,
            EngagementSnapshot.pack_id == pack_id,
        )
        .first()
    )

    if existing:
        existing.esl_score = esl_composite
        existing.engagement_type = recommendation_type
        existing.stress_volatility_index = svi
        existing.communication_stability_index = csi
        existing.sustained_pressure_index = spi
        existing.cadence_blocked = cadence_blocked
        existing.explain = explain
        existing.outreach_score = outreach_score
        existing.esl_decision = esl_decision
        existing.esl_reason_code = esl_reason_code
        existing.sensitivity_level = sensitivity_level
        db.commit()
        db.refresh(existing)
        return existing

    snapshot = EngagementSnapshot(
        company_id=company_id,
        as_of=as_of,
        esl_score=esl_composite,
        engagement_type=recommendation_type,
        stress_volatility_index=svi,
        communication_stability_index=csi,
        sustained_pressure_index=spi,
        cadence_blocked=cadence_blocked,
        explain=explain,
        outreach_score=outreach_score,
        pack_id=pack_id,
        esl_decision=esl_decision,
        esl_reason_code=esl_reason_code,
        sensitivity_level=sensitivity_level,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot
