"""Resolve event-like list from core SignalInstances for scoring (Issue #287, M3).

Used by snapshot_writer when core_pack_id is set: "what signals exist" comes from
core instances; evidence_event_ids (or last_seen fallback) supplies event_time for decay.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import SignalEvent, SignalInstance

# Cap evidence_event_ids resolved per company to avoid huge IN clauses (Issue #287 follow-up).
MAX_EVIDENCE_EVENT_IDS_PER_COMPANY: int = 2000


def get_event_like_list_from_core_instances(
    db: Session,
    company_id: int,
    as_of: date,
    core_pack_id: UUID,
) -> list[Any]:
    """Build event-like list from core SignalInstances for compute_readiness.

    Loads core SignalInstances (entity_id=company_id, pack_id=core_pack_id). For each
    instance: if evidence_event_ids is present, resolve to SignalEvents (batched:
    one query per company for all evidence IDs, then dedupe); otherwise add one
    synthetic event with signal_id as event_type, last_seen as event_time, instance
    confidence. Only events within (as_of - 365 days, as_of] are included. Evidence
    IDs are capped at MAX_EVIDENCE_EVENT_IDS_PER_COMPANY to avoid oversized IN clauses.

    Returns list of objects with .event_type, .event_time, .confidence (compatible
    with readiness_engine _EventLike protocol).
    """
    cutoff_dt = datetime.combine(as_of - timedelta(days=365), datetime.min.time())
    cutoff_dt = cutoff_dt.replace(tzinfo=UTC)

    instances = (
        db.query(SignalInstance)
        .filter(
            SignalInstance.entity_id == company_id,
            SignalInstance.pack_id == core_pack_id,
        )
        .all()
    )
    if not instances:
        return []

    event_like: list[Any] = []
    all_evidence_ids: list[int] = []
    for inst in instances:
        if inst.evidence_event_ids:
            ids = [x for x in inst.evidence_event_ids if isinstance(x, int)]
            all_evidence_ids.extend(ids)

    if all_evidence_ids:
        # Batch load: one query for all evidence events in window (avoids N+1).
        unique_ids = list(dict.fromkeys(all_evidence_ids))[:MAX_EVIDENCE_EVENT_IDS_PER_COMPANY]
        events_batch = (
            db.query(SignalEvent)
            .filter(
                SignalEvent.id.in_(unique_ids),
                SignalEvent.event_time >= cutoff_dt,
            )
            .order_by(SignalEvent.event_time.desc())
            .all()
        )
        seen: set[int] = set()
        for ev in events_batch:
            if ev.id in seen:
                continue
            seen.add(ev.id)
            event_like.append(ev)

    for inst in instances:
        if inst.evidence_event_ids:
            continue
        # Fallback: one synthetic event per instance (Issue #287 compatibility)
        t = inst.last_seen or inst.first_seen
        if t is None:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        if t < cutoff_dt:
            continue
        conf = inst.confidence if inst.confidence is not None else 0.7
        event_like.append(_SyntheticEvent(inst.signal_id, t, conf))

    # Sort by event_time desc to match existing snapshot_writer behavior
    event_like.sort(
        key=lambda e: getattr(e, "event_time", datetime.min.replace(tzinfo=UTC)), reverse=True
    )
    return event_like


class _SyntheticEvent:
    """Event-like object for compute_readiness when evidence_event_ids is missing."""

    __slots__ = ("event_type", "event_time", "confidence")

    def __init__(self, event_type: str, event_time: datetime, confidence: float) -> None:
        self.event_type = event_type
        self.event_time = event_time
        self.confidence = confidence
