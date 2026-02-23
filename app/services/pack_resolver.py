"""Pack resolution for default/active pack (Issue #189).

V3 constraint: one active pack per workspace. Until workspaces exist,
returns fractional_cto_v1 pack for single-tenant compatibility.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.signal_pack import SignalPack

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)


def resolve_pack(db: Session, pack_id: UUID) -> Pack | None:
    """Load Pack from DB by UUID (Issue #189, Plan Step 3).

    Queries SignalPack for pack_id and version, loads pack config from filesystem.
    Returns None if pack not found or load fails (fallback to default constants).
    """
    from app.packs.loader import load_pack

    row = db.query(SignalPack).filter(SignalPack.id == pack_id).first()
    if not row:
        return None
    try:
        return load_pack(row.pack_id, row.version)
    except (FileNotFoundError, ValueError) as e:
        logger.warning("Could not load pack %s v%s: %s", row.pack_id, row.version, e)
        return None


def get_default_pack_id(db: Session) -> UUID | None:
    """Return the fractional_cto_v1 pack UUID, or None if not installed."""
    row = (
        db.query(SignalPack.id)
        .filter(SignalPack.pack_id == "fractional_cto_v1", SignalPack.version == "1")
        .first()
    )
    return row[0] if row else None
