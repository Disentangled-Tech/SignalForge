"""Lead feed query service (Phase 4, Issue #225).

Reads from lead_feed projection for briefing and weekly review.
Returns lead cards with composite_score, outreach_score, esl_decision, etc.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.company import Company
from app.models.engagement_snapshot import EngagementSnapshot
from app.models.lead_feed import LeadFeed
from app.models.readiness_snapshot import ReadinessSnapshot


def get_entity_ids_from_feed(
    db: Session,
    workspace_id: str | UUID,
    pack_id: UUID,
    as_of: date,
    *,
    limit: int = 50,
    min_composite: int = 0,
    sort_by: str = "composite_score",
) -> list[int]:
    """Return entity_ids from lead_feed for workspace/pack/as_of.

    Sorted by composite_score desc or last_seen desc.
    Used for dual-path: feed provides entity list; caller joins for full data.
    """
    ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
    pack_uuid = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id

    q = (
        db.query(LeadFeed.entity_id)
        .filter(
            LeadFeed.workspace_id == ws_uuid,
            LeadFeed.pack_id == pack_uuid,
            LeadFeed.as_of == as_of,
            LeadFeed.composite_score >= min_composite,
        )
    )
    if sort_by == "last_seen":
        q = q.order_by(LeadFeed.last_seen.desc())
    else:
        q = q.order_by(LeadFeed.composite_score.desc())
    rows = q.limit(limit).all()
    return [r[0] for r in rows]


def feed_has_data(
    db: Session,
    workspace_id: str | UUID,
    pack_id: UUID,
    as_of: date,
) -> bool:
    """Return True if lead_feed has rows for workspace/pack/as_of."""
    ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
    pack_uuid = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id
    return (
        db.query(LeadFeed.entity_id)
        .filter(
            LeadFeed.workspace_id == ws_uuid,
            LeadFeed.pack_id == pack_uuid,
            LeadFeed.as_of == as_of,
        )
        .limit(1)
        .first()
        is not None
    )


def get_leads_from_feed(
    db: Session,
    workspace_id: str | UUID,
    pack_id: UUID,
    as_of: date,
    *,
    limit: int = 100,
    offset: int = 0,
    sort_by: str = "composite_score",
    outreach_score_threshold: int = 30,
) -> list[dict]:
    """Query lead_feed for workspace/pack/as_of.

    Returns list of lead cards: entity_id, composite_score, outreach_score,
    top_signal_ids, esl_decision, sensitivity_level, last_seen, etc.

    Sort options: composite_score (DESC), last_seen (DESC).
    Filters by outreach_score_threshold when outreach_score available from join.
    """
    ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id

    order_col = LeadFeed.composite_score.desc()
    if sort_by == "last_seen":
        order_col = LeadFeed.last_seen.desc().nullslast()

    pack_uuid = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id
    rows = (
        db.query(LeadFeed)
        .filter(
            LeadFeed.workspace_id == ws_uuid,
            LeadFeed.pack_id == pack_uuid,
            LeadFeed.as_of == as_of,
        )
        .order_by(order_col)
        .offset(offset)
        .limit(limit * 2)  # Fetch extra for threshold filtering
        .all()
    )

    if not rows:
        return []

    entity_ids = [r.entity_id for r in rows]
    pack_filter = or_(
        EngagementSnapshot.pack_id == pack_uuid,
        EngagementSnapshot.pack_id.is_(None),
    )
    es_rows = (
        db.query(EngagementSnapshot)
        .filter(
            EngagementSnapshot.company_id.in_(entity_ids),
            EngagementSnapshot.as_of == as_of,
            pack_filter,
        )
        .all()
    )
    es_by_entity = {es.company_id: es for es in es_rows}

    from app.services.esl.esl_engine import compute_outreach_score

    result: list[dict] = []
    for row in rows:
        es = es_by_entity.get(row.entity_id)
        if es and es.outreach_score is not None:
            outreach_score = es.outreach_score
        elif es and es.esl_score is not None:
            outreach_score = compute_outreach_score(row.composite_score, es.esl_score)
        else:
            outreach_score = row.composite_score

        if outreach_score < outreach_score_threshold:
            continue
        result.append({
            "entity_id": row.entity_id,
            "composite_score": row.composite_score,
            "outreach_score": outreach_score,
            "top_signal_ids": row.top_signal_ids or [],
            "esl_decision": row.esl_decision,
            "sensitivity_level": row.sensitivity_level,
            "last_seen": row.last_seen,
            "outreach_status_summary": row.outreach_status_summary,
            "as_of": row.as_of,
        })
        if len(result) >= limit:
            break

    return result


def get_emerging_companies_from_feed(
    db: Session,
    as_of: date,
    *,
    workspace_id: str | UUID | None = None,
    pack_id: UUID | None = None,
    limit: int = 5,
    outreach_score_threshold: int = 30,
) -> list[tuple[ReadinessSnapshot, EngagementSnapshot, Company]]:
    """Get emerging companies from lead_feed when populated.

    Returns same shape as get_emerging_companies: list of (RS, ES, Company).
    Batch-joins to ReadinessSnapshot, EngagementSnapshot, Company for full data.
    """
    from app.pipeline.stages import DEFAULT_WORKSPACE_ID
    from app.services.pack_resolver import get_default_pack_id, get_pack_for_workspace

    ws_id = str(workspace_id or DEFAULT_WORKSPACE_ID)
    pack = pack_id or get_pack_for_workspace(db, ws_id) or get_default_pack_id(db)
    if pack is None:
        return []

    pack_uuid = UUID(str(pack)) if isinstance(pack, str) else pack
    ws_uuid = UUID(ws_id)

    if not feed_has_data(db, ws_uuid, pack_uuid, as_of):
        return []

    leads = get_leads_from_feed(
        db,
        ws_uuid,
        pack_uuid,
        as_of,
        limit=limit,
        outreach_score_threshold=outreach_score_threshold,
        sort_by="composite_score",
    )

    if not leads:
        return []

    entity_ids = [lead["entity_id"] for lead in leads]
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
        .options(joinedload(ReadinessSnapshot.company))
        .filter(
            ReadinessSnapshot.company_id.in_(entity_ids),
            ReadinessSnapshot.as_of == as_of,
            pack_filter,
        )
        .all()
    )

    by_entity: dict[int, tuple[ReadinessSnapshot, EngagementSnapshot, Company]] = {}
    for rs, es in pairs:
        if rs.company:
            by_entity[rs.company_id] = (rs, es, rs.company)

    result: list[tuple[ReadinessSnapshot, EngagementSnapshot, Company]] = []
    for lead in leads:
        eid = lead["entity_id"]
        if eid in by_entity:
            result.append(by_entity[eid])
        if len(result) >= limit:
            break

    return result


def get_weekly_review_companies_from_feed(
    db: Session,
    as_of: date,
    *,
    workspace_id: str | UUID | None = None,
    pack_id: UUID | None = None,
    limit: int = 5,
    outreach_score_threshold: int = 30,
) -> list[dict]:
    """Get weekly review companies from lead_feed when populated.

    Returns same shape as get_weekly_review_companies: list of dicts with
    company, readiness_snapshot, engagement_snapshot, outreach_score, etc.
    Applies cooldown check via OutreachHistory.
    """
    from app.pipeline.stages import DEFAULT_WORKSPACE_ID
    from app.services.esl.esl_gate_filter import get_effective_engagement_type
    from app.services.outreach_history import check_outreach_cooldown
    from app.services.pack_resolver import get_default_pack_id, get_pack_for_workspace

    ws_id = str(workspace_id or DEFAULT_WORKSPACE_ID)
    pack = pack_id or get_pack_for_workspace(db, ws_id) or get_default_pack_id(db)
    if pack is None:
        return []

    pack_uuid = UUID(str(pack)) if isinstance(pack, str) else pack
    ws_uuid = UUID(ws_id)

    if not feed_has_data(db, ws_uuid, pack_uuid, as_of):
        return []

    leads = get_leads_from_feed(
        db,
        ws_uuid,
        pack_uuid,
        as_of,
        limit=limit * 3,  # Extra for cooldown filtering
        outreach_score_threshold=outreach_score_threshold,
        sort_by="composite_score",
    )

    if not leads:
        return []

    entity_ids = [lead["entity_id"] for lead in leads]
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
        .options(joinedload(ReadinessSnapshot.company))
        .filter(
            ReadinessSnapshot.company_id.in_(entity_ids),
            ReadinessSnapshot.as_of == as_of,
            pack_filter,
        )
        .all()
    )

    by_entity: dict[int, tuple[ReadinessSnapshot, EngagementSnapshot, Company]] = {}
    for rs, es in pairs:
        if rs.company:
            by_entity[rs.company_id] = (rs, es, rs.company)

    as_of_dt = datetime.combine(as_of, datetime.min.time()).replace(tzinfo=UTC)
    results: list[dict] = []
    for lead in leads:
        if len(results) >= limit:
            break
        eid = lead["entity_id"]
        if eid not in by_entity:
            continue
        rs, es, company = by_entity[eid]
        cooldown = check_outreach_cooldown(db, company.id, as_of_dt)
        if not cooldown.allowed:
            continue
        outreach_score = es.outreach_score if es.outreach_score is not None else lead["outreach_score"]
        effective_type = get_effective_engagement_type(
            es.engagement_type, es.explain, es.esl_decision
        )
        results.append({
            "company_id": company.id,
            "company": company,
            "readiness_snapshot": rs,
            "engagement_snapshot": es,
            "outreach_score": outreach_score,
            "effective_engagement_type": effective_type,
            "explain": {"readiness": rs.explain or {}, "engagement": es.explain or {}},
        })

    return results
