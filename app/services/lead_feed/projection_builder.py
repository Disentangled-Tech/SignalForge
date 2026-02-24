"""Lead feed projection builder (Phase 1, Issue #225, ADR-004).

Builds and upserts lead_feed rows from ReadinessSnapshot + EngagementSnapshot.
Idempotent: replace existing row for (workspace_id, pack_id, entity_id).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.engagement_snapshot import EngagementSnapshot
from app.models.lead_feed import LeadFeed
from app.models.outreach_history import OutreachHistory
from app.models.readiness_snapshot import ReadinessSnapshot
from app.models.signal_instance import SignalInstance
from app.services.esl.esl_gate_filter import is_suppressed_from_engagement


def _top_signal_ids_from_explain(explain: dict | None, limit: int = 8) -> list[str]:
    """Extract top signal_ids from ReadinessSnapshot explain.top_events.

    top_events items have event_type (maps to signal_id in taxonomy).
    """
    if not explain:
        return []
    top_events = explain.get("top_events") or []
    result: list[str] = []
    seen: set[str] = set()
    for ev in top_events[:limit]:
        etype = ev.get("event_type") or ""
        if etype and etype not in seen:
            seen.add(etype)
            result.append(etype)
    return result


def _batch_last_seen_for_entities(
    db: Session, entity_ids: list[int], pack_id: UUID | None
) -> dict[int, datetime | None]:
    """Latest last_seen per entity from SignalInstance (pack-scoped). Batched to avoid N+1."""
    if not entity_ids:
        return {}
    from sqlalchemy import func

    subq = (
        db.query(
            SignalInstance.entity_id,
            func.max(SignalInstance.last_seen).label("last_seen"),
        )
        .filter(
            SignalInstance.entity_id.in_(entity_ids),
            SignalInstance.last_seen.isnot(None),
        )
    )
    if pack_id is not None:
        subq = subq.filter(
            or_(
                SignalInstance.pack_id == pack_id,
                SignalInstance.pack_id.is_(None),
            )
        )
    rows = subq.group_by(SignalInstance.entity_id).all()
    return {r.entity_id: r.last_seen for r in rows}


def _batch_outreach_summary_for_entities(
    db: Session,
    entity_ids: list[int],
    workspace_id: UUID | str | None = None,
) -> dict[int, dict | None]:
    """Latest outreach_status_summary per entity. Batched to avoid N+1.

    When workspace_id is provided, filters OutreachHistory by workspace_id
    to avoid cross-tenant leakage. When None, uses all outreach (legacy).
    """
    if not entity_ids:
        return {}
    q = (
        db.query(OutreachHistory)
        .filter(OutreachHistory.company_id.in_(entity_ids))
    )
    if workspace_id is not None:
        ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
        q = q.filter(OutreachHistory.workspace_id == ws_uuid)
    all_rows = q.order_by(
        OutreachHistory.company_id, OutreachHistory.sent_at.desc()
    ).all()
    result: dict[int, dict | None] = dict.fromkeys(entity_ids, None)
    for oh in all_rows:
        if result[oh.company_id] is None:
            result[oh.company_id] = {
                "last_sent_at": oh.sent_at.isoformat() if oh.sent_at else None,
                "outcome": oh.outcome,
                "outreach_type": oh.outreach_type,
            }
    return result


def upsert_lead_feed_row(
    db: Session,
    workspace_id: UUID | str,
    pack_id: UUID | str,
    entity_id: int,
    *,
    composite_score: int,
    top_signal_ids: list[str] | None = None,
    esl_decision: str | None = None,
    sensitivity_level: str | None = None,
    last_seen: datetime | None = None,
    outreach_status_summary: dict | None = None,
    as_of: date,
) -> LeadFeed:
    """Upsert a single lead_feed row. Replaces existing for (workspace_id, pack_id, entity_id).

    Idempotent: safe to call multiple times for the same entity.
    """
    ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
    pack_uuid = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id

    existing = (
        db.query(LeadFeed)
        .filter(
            LeadFeed.workspace_id == ws_uuid,
            LeadFeed.pack_id == pack_uuid,
            LeadFeed.entity_id == entity_id,
        )
        .first()
    )

    now = datetime.now(UTC)
    row_data = {
        "composite_score": composite_score,
        "top_signal_ids": top_signal_ids or [],
        "esl_decision": esl_decision,
        "sensitivity_level": sensitivity_level,
        "last_seen": last_seen,
        "outreach_status_summary": outreach_status_summary,
        "as_of": as_of,
        "updated_at": now,
    }

    if existing:
        for k, v in row_data.items():
            setattr(existing, k, v)
        db.flush()
        return existing

    row = LeadFeed(
        workspace_id=ws_uuid,
        pack_id=pack_uuid,
        entity_id=entity_id,
        **row_data,
    )
    db.add(row)
    db.flush()
    return row


def upsert_lead_feed_from_snapshots(
    db: Session,
    workspace_id: UUID | str,
    pack_id: UUID | str,
    as_of: date,
    readiness_snapshot: ReadinessSnapshot,
    engagement_snapshot: EngagementSnapshot,
) -> LeadFeed | None:
    """Upsert a single lead_feed row from ReadinessSnapshot + EngagementSnapshot.

    Used by score job for incremental updates (Phase 3). Skips suppressed entities.
    Returns None when entity is suppressed.
    """
    if is_suppressed_from_engagement(
        engagement_snapshot.esl_decision, engagement_snapshot.explain
    ):
        return None
    min_thresh = (readiness_snapshot.explain or {}).get("minimum_threshold", 0) or 0
    if min_thresh > 0 and readiness_snapshot.composite < min_thresh:
        return None

    entity_id = readiness_snapshot.company_id
    pack_uuid = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id

    ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
    last_seen_by = _batch_last_seen_for_entities(db, [entity_id], pack_uuid)
    outreach_by = _batch_outreach_summary_for_entities(
        db, [entity_id], workspace_id=ws_uuid
    )

    top_signal_ids = _top_signal_ids_from_explain(readiness_snapshot.explain)
    esl_decision = engagement_snapshot.esl_decision or (
        engagement_snapshot.explain or {}
    ).get("esl_decision")
    sensitivity_level = engagement_snapshot.sensitivity_level or (
        engagement_snapshot.explain or {}
    ).get("sensitivity_level")
    last_seen = last_seen_by.get(entity_id)
    if last_seen is None and readiness_snapshot.computed_at:
        last_seen = readiness_snapshot.computed_at
    outreach_summary = outreach_by.get(entity_id)

    return upsert_lead_feed_row(
        db,
        workspace_id,
        pack_id,
        entity_id,
        composite_score=readiness_snapshot.composite,
        top_signal_ids=top_signal_ids,
        esl_decision=esl_decision,
        sensitivity_level=sensitivity_level,
        last_seen=last_seen,
        outreach_status_summary=outreach_summary,
        as_of=as_of,
    )


def refresh_outreach_summary_for_entity(
    db: Session,
    entity_id: int,
    workspace_id: UUID | str | None = None,
) -> int:
    """Refresh outreach_status_summary for lead_feed rows for an entity.

    Called after outreach event (create/update/delete). Returns count of rows updated.
    When workspace_id is provided, updates only lead_feed rows for that workspace
    using workspace-scoped outreach. When None (legacy), updates all rows for entity.
    """
    outreach_by = _batch_outreach_summary_for_entities(
        db, [entity_id], workspace_id=workspace_id
    )
    summary = outreach_by.get(entity_id)

    q = db.query(LeadFeed).filter(LeadFeed.entity_id == entity_id)
    if workspace_id is not None:
        ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
        q = q.filter(LeadFeed.workspace_id == ws_uuid)
    rows = q.all()
    for row in rows:
        row.outreach_status_summary = summary
    if rows:
        db.flush()
    return len(rows)


def build_lead_feed_from_snapshots(
    db: Session,
    workspace_id: UUID | str,
    pack_id: UUID | None,
    as_of: date,
) -> int:
    """Build lead_feed projection from latest ReadinessSnapshot + EngagementSnapshot.

    Joins snapshots for as_of and pack; excludes suppressed entities.
    Upserts one row per entity. Returns count of rows upserted.

    Pack-scoped: when pack_id is set, filters snapshots by pack_id or NULL (legacy).
    """
    ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id

    if pack_id is None:
        return 0

    pack_uuid = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id

    pack_match = or_(
        ReadinessSnapshot.pack_id == EngagementSnapshot.pack_id,
        (ReadinessSnapshot.pack_id.is_(None)) & (EngagementSnapshot.pack_id.is_(None)),
    )
    pack_filter = or_(
        ReadinessSnapshot.pack_id == pack_uuid,
        ReadinessSnapshot.pack_id.is_(None),
    )

    pairs = (
        db.query(ReadinessSnapshot, EngagementSnapshot)
        .join(
            EngagementSnapshot,
            (ReadinessSnapshot.company_id == EngagementSnapshot.company_id)
            & (ReadinessSnapshot.as_of == EngagementSnapshot.as_of)
            & pack_match,
        )
        .filter(ReadinessSnapshot.as_of == as_of, pack_filter)
        .all()
    )

    def _should_include(rs: ReadinessSnapshot, es: EngagementSnapshot) -> bool:
        if is_suppressed_from_engagement(es.esl_decision, es.explain):
            return False
        min_thresh = (rs.explain or {}).get("minimum_threshold", 0) or 0
        if min_thresh > 0 and rs.composite < min_thresh:
            return False
        return True

    entity_ids = [rs.company_id for rs, es in pairs if _should_include(rs, es)]
    last_seen_by_entity = _batch_last_seen_for_entities(db, entity_ids, pack_uuid)
    outreach_by_entity = _batch_outreach_summary_for_entities(
        db, entity_ids, workspace_id=ws_uuid
    )

    count = 0
    for rs, es in pairs:
        if not _should_include(rs, es):
            continue

        entity_id = rs.company_id
        top_signal_ids = _top_signal_ids_from_explain(rs.explain)
        esl_decision = es.esl_decision or (es.explain or {}).get("esl_decision")
        sensitivity_level = es.sensitivity_level or (es.explain or {}).get(
            "sensitivity_level"
        )
        last_seen = last_seen_by_entity.get(entity_id)
        if last_seen is None and rs.computed_at:
            last_seen = rs.computed_at

        outreach_summary = outreach_by_entity.get(entity_id)

        upsert_lead_feed_row(
            db,
            ws_uuid,
            pack_uuid,
            entity_id,
            composite_score=rs.composite,
            top_signal_ids=top_signal_ids,
            esl_decision=esl_decision,
            sensitivity_level=sensitivity_level,
            last_seen=last_seen,
            outreach_status_summary=outreach_summary,
            as_of=as_of,
        )
        count += 1

    return count
