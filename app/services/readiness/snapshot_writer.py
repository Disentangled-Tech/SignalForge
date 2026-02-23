"""Write ReadinessSnapshot to DB (Issue #87)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Company, ReadinessSnapshot, SignalEvent
from app.services.pack_resolver import get_default_pack_id, resolve_pack
from app.services.readiness.readiness_engine import compute_readiness


def write_readiness_snapshot(
    db: Session,
    company_id: int,
    as_of: date,
    company_status: str | None = None,
    pack_id=None,
) -> ReadinessSnapshot | None:
    """Compute readiness from SignalEvents and persist ReadinessSnapshot.

    Queries SignalEvents for company in last 365 days. If no events, returns None.
    Upserts snapshot (unique on company_id, as_of, pack_id). Issue #189.
    """
    pack_id = pack_id or get_default_pack_id(db)
    if pack_id is None:
        return None

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None

    cutoff_dt = datetime.combine(as_of - timedelta(days=365), datetime.min.time())
    cutoff_dt = cutoff_dt.replace(tzinfo=UTC)
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
        .order_by(SignalEvent.event_time.desc())
        .all()
    )

    if not events:
        return None

    pack = resolve_pack(db, pack_id) if pack_id else None
    result = compute_readiness(
        events=events,
        as_of=as_of,
        company_status=company_status,
        pack=pack,
    )

    # Delta: today.composite - prev.composite (v2-spec §6.4, Issue #104)
    prev_snapshot = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of == as_of - timedelta(days=1),
            ReadinessSnapshot.pack_id == pack_id,
        )
        .first()
    )
    delta_1d = result["composite"] - prev_snapshot.composite if prev_snapshot is not None else 0
    result["explain"]["delta_1d"] = delta_1d

    existing = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of == as_of,
            ReadinessSnapshot.pack_id == pack_id,
        )
        .first()
    )

    if existing:
        existing.momentum = result["momentum"]
        existing.complexity = result["complexity"]
        existing.pressure = result["pressure"]
        existing.leadership_gap = result["leadership_gap"]
        existing.composite = result["composite"]
        existing.explain = result["explain"]
        db.commit()
        db.refresh(existing)
        return existing

    snapshot = ReadinessSnapshot(
        company_id=company_id,
        as_of=as_of,
        momentum=result["momentum"],
        complexity=result["complexity"],
        pressure=result["pressure"],
        leadership_gap=result["leadership_gap"],
        composite=result["composite"],
        explain=result["explain"],
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot
