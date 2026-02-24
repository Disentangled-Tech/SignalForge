"""Deriver engine: populate signal_instances from SignalEvents (Phase 2, Issue #192).

Applies pack derivers (passthrough: event_type -> signal_id) to produce
entity-level signal instances. Idempotent: upsert by (entity_id, signal_id, pack_id).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.job_run import JobRun
from app.models.signal_event import SignalEvent
from app.models.signal_instance import SignalInstance
from app.services.pack_resolver import get_default_pack_id, resolve_pack

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)


def _build_passthrough_map(pack: Pack | None) -> dict[str, str]:
    """Build event_type -> signal_id map from pack derivers.passthrough."""
    if not pack or not pack.derivers:
        return {}
    # derivers.yaml: top-level "derivers" key, then "passthrough" list
    inner = pack.derivers.get("derivers") or pack.derivers
    passthrough = inner.get("passthrough") if isinstance(inner, dict) else []
    if not isinstance(passthrough, list):
        return {}
    result: dict[str, str] = {}
    for item in passthrough:
        if isinstance(item, dict):
            etype = item.get("event_type")
            sid = item.get("signal_id")
            if etype and sid:
                result[str(etype)] = str(sid)
    return result


def run_deriver(
    db: Session,
    workspace_id: str | UUID | None = None,
    pack_id: str | UUID | None = None,
    company_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Run deriver: read SignalEvents, apply pack passthrough, upsert signal_instances.

    Scopes to pack_id (or default pack). Events with company_id is None are skipped.
    Idempotent: re-run produces same signal_instances (upsert by natural key).
    Creates JobRun record for audit.

    Args:
        company_ids: Optional list of company IDs to scope events (test-only; not
            exposed via API). When None, processes all events for the pack.

    Returns:
        dict with status, job_run_id, instances_upserted, events_processed, events_skipped
    """
    pack_uuid = pack_id or get_default_pack_id(db)
    if not pack_uuid:
        logger.warning("No pack_id available; deriver skipped")
        return {
            "status": "skipped",
            "job_run_id": None,
            "instances_upserted": 0,
            "events_processed": 0,
            "events_skipped": 0,
            "error": "No pack available",
        }

    pack_uuid = UUID(str(pack_uuid)) if isinstance(pack_uuid, str) else pack_uuid

    job = JobRun(job_type="derive", status="running")
    if workspace_id is not None:
        job.workspace_id = (
            UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
        )
    job.pack_id = pack_uuid
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        return _run_deriver_core(db, job, pack_uuid, company_ids=company_ids)
    except Exception as exc:
        logger.exception("Deriver job failed")
        job.finished_at = datetime.now(UTC)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        return {
            "status": "failed",
            "job_run_id": job.id,
            "instances_upserted": 0,
            "events_processed": 0,
            "events_skipped": 0,
            "error": str(exc),
        }


def _run_deriver_core(
    db: Session,
    job: JobRun,
    pack_uuid: UUID,
    company_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Core deriver logic. Updates job in-place, commits, returns result dict."""
    pack = resolve_pack(db, pack_uuid)
    passthrough = _build_passthrough_map(pack)

    if not passthrough:
        logger.warning("Pack has no passthrough derivers; deriver skipped")
        job.finished_at = datetime.now(UTC)
        job.status = "skipped"
        job.error_message = "No passthrough derivers in pack"
        db.commit()
        return {
            "status": "skipped",
            "job_run_id": job.id,
            "instances_upserted": 0,
            "events_processed": 0,
            "events_skipped": 0,
            "error": "No passthrough derivers in pack",
        }

    # Query SignalEvents: pack_id matches; optionally scope to company_ids (for tests)
    q = db.query(SignalEvent).filter(SignalEvent.pack_id == pack_uuid)
    if company_ids is not None:
        q = q.filter(SignalEvent.company_id.in_(company_ids))
    events = q.all()

    # Aggregate by (entity_id, signal_id): min first_seen, max last_seen, latest confidence
    # Passthrough: event_type -> signal_id
    aggregated: dict[tuple[int, str], dict[str, Any]] = {}
    events_skipped = 0

    for ev in events:
        if ev.company_id is None:
            events_skipped += 1
            continue
        signal_id = passthrough.get(ev.event_type)
        if not signal_id:
            events_skipped += 1
            continue

        key = (ev.company_id, signal_id)
        if key not in aggregated:
            aggregated[key] = {
                "entity_id": ev.company_id,
                "signal_id": signal_id,
                "first_seen": ev.event_time,
                "last_seen": ev.event_time,
                "confidence": ev.confidence,
            }
        else:
            agg = aggregated[key]
            if ev.event_time < agg["first_seen"]:
                agg["first_seen"] = ev.event_time
            if ev.event_time > agg["last_seen"]:
                agg["last_seen"] = ev.event_time
            if ev.confidence is not None and (
                agg["confidence"] is None or ev.confidence > agg["confidence"]
            ):
                agg["confidence"] = ev.confidence

    events_processed = len(events) - events_skipped

    # Batch upsert: INSERT ... ON CONFLICT DO UPDATE (avoids N+1)
    def _ensure_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt

    values = []
    for (entity_id, signal_id), agg in aggregated.items():
        first_seen = _ensure_utc(agg["first_seen"])
        last_seen = _ensure_utc(agg["last_seen"])
        values.append({
            "entity_id": entity_id,
            "signal_id": signal_id,
            "pack_id": pack_uuid,
            "strength": 1.0,
            "confidence": agg["confidence"],
            "first_seen": first_seen,
            "last_seen": last_seen,
        })

    if values:
        stmt = insert(SignalInstance).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["entity_id", "signal_id", "pack_id"],
            set_={
                "first_seen": func.least(
                    func.coalesce(SignalInstance.first_seen, stmt.excluded.first_seen),
                    func.coalesce(stmt.excluded.first_seen, SignalInstance.first_seen),
                ),
                "last_seen": func.greatest(
                    func.coalesce(SignalInstance.last_seen, stmt.excluded.last_seen),
                    func.coalesce(stmt.excluded.last_seen, SignalInstance.last_seen),
                ),
                "confidence": func.coalesce(
                    stmt.excluded.confidence,
                    SignalInstance.confidence,
                ),
                "strength": 1.0,
            },
        )
        db.execute(stmt)

    upserted = len(values)
    job.finished_at = datetime.now(UTC)
    job.status = "completed"
    job.companies_processed = upserted
    job.error_message = None
    db.commit()
    logger.info(
        "Deriver completed: pack_id=%s instances_upserted=%d events_processed=%d events_skipped=%d",
        pack_uuid,
        upserted,
        events_processed,
        events_skipped,
    )
    return {
        "status": "completed",
        "job_run_id": job.id,
        "instances_upserted": upserted,
        "events_processed": events_processed,
        "events_skipped": events_skipped,
    }
