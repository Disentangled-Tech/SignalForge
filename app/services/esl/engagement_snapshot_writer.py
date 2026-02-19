"""Write EngagementSnapshot to DB (Issue #106).

Computes ESL from ReadinessSnapshot, SignalEvents, OutreachHistory, Company.
Runs after readiness scoring; requires ReadinessSnapshot for company/as_of.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Company, EngagementSnapshot, OutreachHistory, ReadinessSnapshot, SignalEvent
from app.services.esl.esl_constants import STABILITY_CAP_THRESHOLD
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


def compute_esl_from_context(
    db: Session,
    company_id: int,
    as_of: date,
) -> dict[str, Any] | None:
    """Compute ESL from DB context without persisting (Issue #106).

    Returns dict with esl_composite, stability_modifier, recommendation_type,
    explain, cadence_blocked, alignment_high. Returns None if no ReadinessSnapshot.
    """
    readiness = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of == as_of,
        )
        .first()
    )
    if not readiness:
        return None

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None

    cutoff_dt = datetime.combine(as_of - timedelta(days=365), datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    events = (
        db.query(SignalEvent)
        .filter(
            SignalEvent.company_id == company_id,
            SignalEvent.event_time >= cutoff_dt,
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
    svi = compute_svi(events, as_of)
    spi = compute_spi(pressure_snapshots, as_of)
    csi = compute_csi(events, as_of)
    sm = compute_stability_modifier(svi, spi, csi)
    cm = compute_cadence_modifier(last_outreach, as_of)
    am = compute_alignment_modifier(company.alignment_ok_to_contact)
    esl_composite = compute_esl_composite(be, sm, cm, am)
    recommendation_type = map_esl_to_recommendation(esl_composite)

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

    return {
        "esl_composite": esl_composite,
        "stability_modifier": sm,
        "recommendation_type": recommendation_type,
        "explain": explain,
        "cadence_blocked": cadence_blocked,
        "alignment_high": company.alignment_ok_to_contact is not False,
        "trs": readiness.composite,
    }


def write_engagement_snapshot(
    db: Session,
    company_id: int,
    as_of: date,
) -> EngagementSnapshot | None:
    """Compute ESL from context and persist EngagementSnapshot.

    Requires ReadinessSnapshot for company/as_of. Fetches SignalEvents (365d),
    OutreachHistory (last sent), Company alignment. Upserts EngagementSnapshot.
    """
    ctx = compute_esl_from_context(db, company_id, as_of)
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

    existing = (
        db.query(EngagementSnapshot)
        .filter(
            EngagementSnapshot.company_id == company_id,
            EngagementSnapshot.as_of == as_of,
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
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot
