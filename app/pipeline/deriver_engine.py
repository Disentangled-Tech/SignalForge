"""Deriver engine: populate signal_instances from SignalEvents (Phase 2, Issue #192).

Applies derivers (passthrough: event_type -> signal_id; pattern: regex on
title/summary) to produce entity-level signal instances. Idempotent: upsert by
(entity_id, signal_id, pack_id).

Phase 1 (Issue #173): pattern derivers support.
Issue #285, Milestone 6: derive uses core derivers only; pack deriver fallback removed.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core_derivers.loader import get_core_passthrough_map, get_core_pattern_derivers
from app.models.job_run import JobRun
from app.models.signal_event import SignalEvent
from app.models.signal_instance import SignalInstance
from app.packs.schemas import ALLOWED_PATTERN_SOURCE_FIELDS
from app.services.pack_resolver import get_default_pack_id, resolve_pack

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)

# Default fields to search for pattern derivers when source_fields not specified
_DEFAULT_PATTERN_SOURCE_FIELDS = ("title", "summary")


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


def _build_pattern_derivers(pack: Pack | None) -> list[dict[str, Any]]:
    """Build list of pattern deriver configs from pack derivers.pattern.

    Each entry: {signal_id, pattern, source_fields, min_confidence}.
    Patterns are precompiled for runtime (ADR-008).
    """
    if not pack or not pack.derivers:
        return []
    inner = pack.derivers.get("derivers") or pack.derivers
    pattern_list = inner.get("pattern") if isinstance(inner, dict) else []
    if not isinstance(pattern_list, list):
        return []
    result: list[dict[str, Any]] = []
    for item in pattern_list:
        if not isinstance(item, dict):
            continue
        sid = item.get("signal_id")
        pat_str = item.get("pattern") or item.get("regex")
        if not sid or not pat_str:
            continue
        try:
            compiled = re.compile(pat_str)
        except re.error:
            logger.warning("Invalid pattern deriver regex for signal_id=%s, skipping", sid)
            continue
        source_fields = item.get("source_fields")
        if source_fields is None:
            source_fields = list(_DEFAULT_PATTERN_SOURCE_FIELDS)
        elif not isinstance(source_fields, list):
            source_fields = list(_DEFAULT_PATTERN_SOURCE_FIELDS)
        else:
            # Filter by schema-validated whitelist (title, summary, url, source)
            source_fields = [f for f in source_fields if f in ALLOWED_PATTERN_SOURCE_FIELDS]
            if not source_fields:
                source_fields = list(_DEFAULT_PATTERN_SOURCE_FIELDS)
        min_confidence = item.get("min_confidence")
        if min_confidence is not None:
            min_confidence = float(min_confidence)
        result.append(
            {
                "signal_id": str(sid),
                "compiled": compiled,
                "source_fields": source_fields,
                "min_confidence": min_confidence,
            }
        )
    return result


def _load_core_derivers() -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Load core passthrough map and pattern derivers (Issue #285).

    Returns (passthrough_map, pattern_derivers) in the format expected by
    _evaluate_event_derivers. Results come from lru_cached core_derivers module.

    Raises:
        FileNotFoundError: When core derivers.yaml is missing.
        ValueError: When core derivers fail schema validation.
    """
    passthrough_map = get_core_passthrough_map()
    pattern_derivers: list[dict[str, Any]] = list(get_core_pattern_derivers())
    return passthrough_map, pattern_derivers


def _evaluate_event_derivers(
    ev: SignalEvent,
    passthrough_map: Mapping[str, str],
    pattern_derivers: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Evaluate all derivers for a single event. Returns list of (signal_id, deriver_type).

    Passthrough: event_type -> signal_id (exact match).
    Pattern: regex match on title/summary (or source_fields); min_confidence filter.
    deriver_type is 'passthrough' or 'pattern'.
    """
    result: list[tuple[str, str]] = []
    seen: set[str] = set()

    # Passthrough: event_type -> signal_id
    sid = passthrough_map.get(ev.event_type)
    if sid and sid not in seen:
        result.append((sid, "passthrough"))
        seen.add(sid)

    # Pattern: match against source_fields
    ev_confidence = ev.confidence if ev.confidence is not None else 0.7
    for cfg in pattern_derivers:
        if cfg["min_confidence"] is not None and ev_confidence < cfg["min_confidence"]:
            continue
        text_parts: list[str] = []
        for field in cfg["source_fields"]:
            val = getattr(ev, field, None)
            if val is not None and isinstance(val, str):
                text_parts.append(val)
        text = " ".join(text_parts) if text_parts else ""
        if cfg["compiled"].search(text):
            sid = cfg["signal_id"]
            if sid not in seen:
                result.append((sid, "pattern"))
                seen.add(sid)

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
    """Core deriver logic. Updates job in-place, commits, returns result dict.

    Uses core derivers only (Issue #285, Milestone 6). If core derivers fail to
    load (FileNotFoundError, ValueError), the exception propagates and the job
    is marked failed by run_deriver.
    """
    resolve_pack(db, pack_uuid)  # ensure pack exists for job/scoping

    passthrough, pattern_derivers = _load_core_derivers()
    logger.debug(
        "Using core derivers: passthrough=%d patterns=%d",
        len(passthrough),
        len(pattern_derivers),
    )

    if not passthrough and not pattern_derivers:
        logger.warning("No derivers available (core or pack); deriver skipped")
        job.finished_at = datetime.now(UTC)
        job.status = "skipped"
        job.error_message = "No passthrough or pattern derivers available"
        db.commit()
        return {
            "status": "skipped",
            "job_run_id": job.id,
            "instances_upserted": 0,
            "events_processed": 0,
            "events_skipped": 0,
            "error": "No passthrough or pattern derivers available",
        }

    # Query SignalEvents: pack_id matches; optionally scope to company_ids (for tests)
    q = db.query(SignalEvent).filter(SignalEvent.pack_id == pack_uuid)
    if company_ids is not None:
        q = q.filter(SignalEvent.company_id.in_(company_ids))
    events = q.all()

    # Aggregate by (entity_id, signal_id): min first_seen, max last_seen, latest confidence
    aggregated: dict[tuple[int, str], dict[str, Any]] = {}
    events_skipped = 0

    for ev in events:
        if ev.company_id is None:
            events_skipped += 1
            continue
        evaluated = _evaluate_event_derivers(ev, passthrough, pattern_derivers)
        if not evaluated:
            events_skipped += 1
            continue

        for signal_id, deriver_type in evaluated:
            logger.info(
                "deriver_triggered pack_id=%s signal_id=%s event_id=%s deriver_type=%s",
                pack_uuid,
                signal_id,
                ev.id,
                deriver_type,
            )
            key = (ev.company_id, signal_id)
            if key not in aggregated:
                aggregated[key] = {
                    "entity_id": ev.company_id,
                    "signal_id": signal_id,
                    "first_seen": ev.event_time,
                    "last_seen": ev.event_time,
                    "confidence": ev.confidence,
                    "evidence_event_ids": [ev.id],
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
                if ev.id not in agg["evidence_event_ids"]:
                    agg["evidence_event_ids"].append(ev.id)

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
        values.append(
            {
                "entity_id": entity_id,
                "signal_id": signal_id,
                "pack_id": pack_uuid,
                "strength": 1.0,
                "confidence": agg["confidence"],
                "first_seen": first_seen,
                "last_seen": last_seen,
                "evidence_event_ids": agg.get("evidence_event_ids"),
            }
        )

    if values:
        stmt = insert(SignalInstance).values(values)
        # Merge evidence_event_ids and deduplicate (avoids unbounded growth on re-runs)
        merged_evidence = text(
            "(SELECT coalesce(jsonb_agg(elem), '[]'::jsonb) FROM ("
            "SELECT DISTINCT jsonb_array_elements("
            "COALESCE(signal_instances.evidence_event_ids, '[]'::jsonb) || "
            "COALESCE(excluded.evidence_event_ids, '[]'::jsonb)"
            ") AS elem) sub)"
        )
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
                "evidence_event_ids": merged_evidence,
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
