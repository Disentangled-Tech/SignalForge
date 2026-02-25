"""Lead feed writer — upsert projection from ReadinessSnapshot + EngagementSnapshot (Phase 3).

Delegates to build_lead_feed_from_snapshots for schema compatibility.
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def upsert_lead_feed(
    db: Session,
    workspace_id: str | UUID,
    pack_id: str | UUID,
    as_of: date,
) -> int:
    """Upsert lead_feed from ReadinessSnapshot + EngagementSnapshot for given date.

    Idempotent: re-run produces same rows (upsert by natural key).
    Delegates to build_lead_feed_from_snapshots for current schema compatibility.
    Returns count of rows upserted.
    """
    from app.services.lead_feed import build_lead_feed_from_snapshots

    count = build_lead_feed_from_snapshots(
        db,
        workspace_id=workspace_id,
        pack_id=pack_id,
        as_of=as_of,
    )
    db.commit()
    ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
    pack_uuid = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id
    logger.info(
        "lead_feed upserted: workspace_id=%s pack_id=%s as_of=%s count=%d",
        ws_uuid,
        pack_uuid,
        as_of,
        count,
    )
    return count
