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
    from app.packs.schemas import ValidationError

    row = db.query(SignalPack).filter(SignalPack.id == pack_id).first()
    if not row:
        return None
    try:
        return load_pack(row.pack_id, row.version)
    except (FileNotFoundError, ValueError, ValidationError) as e:
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


def get_default_pack(db: Session | None = None) -> Pack | None:
    """Return default pack: from db when available, else load from filesystem.

    Phase 2: Used when pack is None. Resolves from db first; if no pack in db,
    loads fractional_cto_v1 from filesystem for backward compatibility.
    """
    if db is not None:
        pack_id = get_default_pack_id(db)
        if pack_id is not None:
            return resolve_pack(db, pack_id)
    try:
        from app.packs.loader import load_pack

        return load_pack("fractional_cto_v1", "1")
    except (FileNotFoundError, ValueError, KeyError):
        return None


def get_discovery_pack_id(db: Session) -> UUID | None:
    """Return the llm_discovery_scout_v0 pack UUID if installed, else None.

    Phase 3: Used when evidence_only=True on run_scan; discovery pack
    surfaces evidence without outreach drafts.
    """
    row = (
        db.query(SignalPack.id)
        .filter(
            SignalPack.pack_id == "llm_discovery_scout_v0",
            SignalPack.version == "1",
        )
        .first()
    )
    return row[0] if row else None


def get_pack_for_workspace(
    db: Session, workspace_id: str | UUID | None
) -> UUID | None:
    """Return the active pack for the workspace, or default pack if workspace has none.

    Phase 3 (Pack Activation Runtime): When workspace has active_pack_id, use it.
    Otherwise fall back to get_default_pack_id(db) for backward compatibility.
    When workspace_id is None (multi_workspace disabled), returns default pack.
    Logs warning when workspace does not exist (avoids silent misattribution).
    """
    from app.models.workspace import Workspace

    if workspace_id is None:
        return get_default_pack_id(db)
    ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
    ws = db.query(Workspace).filter(Workspace.id == ws_uuid).first()
    if ws is None:
        logger.warning(
            "Workspace %s not found; falling back to default pack for pack resolution",
            ws_uuid,
        )
        return get_default_pack_id(db)
    if ws.active_pack_id is not None:
        return ws.active_pack_id
    return get_default_pack_id(db)
