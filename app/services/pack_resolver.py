"""Pack resolution for default/active pack (Issue #189).

V3 constraint: one active pack per workspace. Until workspaces exist,
returns fractional_cto_v1 pack for single-tenant compatibility.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.signal_pack import SignalPack


def get_default_pack_id(db: Session) -> UUID | None:
    """Return the fractional_cto_v1 pack UUID, or None if not installed."""
    row = (
        db.query(SignalPack.id)
        .filter(SignalPack.pack_id == "fractional_cto_v1", SignalPack.version == "1")
        .first()
    )
    return row[0] if row else None
