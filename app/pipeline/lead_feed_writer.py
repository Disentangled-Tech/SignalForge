"""Lead feed writer — upsert projection from ReadinessSnapshot + EngagementSnapshot (Phase 3)."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.engagement_snapshot import EngagementSnapshot
from app.models.lead_feed import LeadFeed
from app.models.readiness_snapshot import ReadinessSnapshot
from app.services.esl.esl_engine import compute_outreach_score

logger = logging.getLogger(__name__)


def upsert_lead_feed(
    db: Session,
    workspace_id: str | UUID,
    pack_id: str | UUID,
    as_of: date,
) -> int:
    """Upsert lead_feed from ReadinessSnapshot + EngagementSnapshot for given date.

    Idempotent: re-run produces same rows (upsert by natural key).
    Uses batch INSERT ... ON CONFLICT DO UPDATE for performance.
    Returns count of rows upserted.
    """
    ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
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

    values = []
    for rs, es in pairs:
        outreach_score = compute_outreach_score(rs.composite, es.esl_score)
        top_reasons = (rs.explain or {}).get("top_events")
        stability_cap = (es.explain or {}).get("stability_cap_triggered", False)
        values.append({
            "workspace_id": ws_uuid,
            "entity_id": rs.company_id,
            "pack_id": pack_uuid,
            "as_of": as_of,
            "composite_score": rs.composite,
            "top_reasons": top_reasons,
            "esl_score": es.esl_score,
            "engagement_type": es.engagement_type,
            "cadence_blocked": es.cadence_blocked,
            "stability_cap_triggered": stability_cap,
            "outreach_score": outreach_score,
        })

    if not values:
        return 0

    stmt = insert(LeadFeed).values(values)
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        constraint="uq_lead_feed_workspace_entity_pack_as_of",
        set_={
            LeadFeed.composite_score: excluded.composite_score,
            LeadFeed.top_reasons: excluded.top_reasons,
            LeadFeed.esl_score: excluded.esl_score,
            LeadFeed.engagement_type: excluded.engagement_type,
            LeadFeed.cadence_blocked: excluded.cadence_blocked,
            LeadFeed.stability_cap_triggered: excluded.stability_cap_triggered,
            LeadFeed.outreach_score: excluded.outreach_score,
            LeadFeed.updated_at: func.now(),
        },
    )
    db.execute(stmt)
    db.commit()
    count = len(values)
    logger.info(
        "lead_feed upserted: workspace_id=%s pack_id=%s as_of=%s count=%d",
        ws_uuid,
        pack_uuid,
        as_of,
        count,
    )
    return count
