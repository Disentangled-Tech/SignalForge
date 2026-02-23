"""Pack resolution for default/active pack (Issue #189, Phase 3).

V3 constraint: one active pack per workspace. When workspace_id is provided,
queries workspaces.active_pack_id; else falls back to fractional_cto_v1
for single-tenant compatibility.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.signal_pack import SignalPack
from app.models.workspace import Workspace

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)


def resolve_pack(db: Session, pack_id: UUID) -> Pack | None:
    """Load Pack from DB by UUID (Issue #189, Plan Step 3).

    Queries SignalPack for pack_id and version, loads pack config from filesystem.
    Returns None if pack not found or load fails (fallback to default constants).
    """
    from app.packs.loader import load_pack
    from app.packs.schemas import ValidationError

    row = db.query(SignalPack).filter(SignalPack.id == pack_id).first()
    if not row:
        return None
    try:
        return load_pack(row.pack_id, row.version)
    except (FileNotFoundError, ValueError, ValidationError) as e:
        logger.warning("Could not load pack %s v%s: %s", row.pack_id, row.version, e)
        return None


def get_default_pack_id(db: Session, workspace_id: UUID | None = None) -> UUID | None:
    """Return active pack UUID for workspace, or fractional_cto_v1 if not workspace-aware.

    When workspace_id is provided and the workspace has active_pack_id set,
    returns that. Otherwise falls back to fractional_cto_v1 pack (single-tenant).
    """
    if workspace_id is not None:
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if ws is not None and ws.active_pack_id is not None:
            return ws.active_pack_id
    # Fallback: fractional_cto_v1 (single-tenant compatibility)
    row = (
        db.query(SignalPack.id)
        .filter(SignalPack.pack_id == "fractional_cto_v1", SignalPack.version == "1")
        .first()
    )
    return row[0] if row else None
