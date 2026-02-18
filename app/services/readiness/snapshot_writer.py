"""Write ReadinessSnapshot to DB (Issue #87)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Company, ReadinessSnapshot, SignalEvent
from app.services.readiness.readiness_engine import compute_readiness


def write_readiness_snapshot(
    db: Session,
    company_id: int,
    as_of: date,
    company_status: str | None = None,
) -> ReadinessSnapshot | None:
    """Compute readiness from SignalEvents and persist ReadinessSnapshot.

    Queries SignalEvents for company in last 365 days. If no events, returns None.
    Upserts snapshot (unique on company_id, as_of).
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None

    cutoff_dt = datetime.combine(as_of - timedelta(days=365), datetime.min.time())
    cutoff_dt = cutoff_dt.replace(tzinfo=timezone.utc)
    events = (
        db.query(SignalEvent)
        .filter(
            SignalEvent.company_id == company_id,
            SignalEvent.event_time >= cutoff_dt,
        )
        .order_by(SignalEvent.event_time.desc())
        .all()
    )

    if not events:
        return None

    result = compute_readiness(
        events=events,
        as_of=as_of,
        company_status=company_status,
    )

    existing = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of == as_of,
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
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot
