"""Admin API — pack metadata and settings (Issue #172, Phase 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_auth
from app.models.signal_pack import SignalPack
from app.models.user import User
from app.services.pack_resolver import get_default_pack_id, resolve_pack

router = APIRouter()


@router.get("/packs")
def list_installed_packs(
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
) -> dict:
    """List installed signal packs with metadata (pack_id, version, name, schema_version)."""
    rows = db.query(SignalPack).filter(SignalPack.is_active).all()
    packs: list[dict] = []
    active_pack_uuid = get_default_pack_id(db)
    for row in rows:
        pack = resolve_pack(db, row.id)
        if pack is not None:
            packs.append(
                {
                    "id": str(row.id),
                    "pack_id": pack.manifest.get("id", ""),
                    "version": pack.manifest.get("version", ""),
                    "name": pack.manifest.get("name", ""),
                    "schema_version": pack.manifest.get("schema_version", ""),
                    "active": row.id == active_pack_uuid,
                }
            )
        else:
            packs.append(
                {
                    "id": str(row.id),
                    "pack_id": row.pack_id,
                    "version": row.version,
                    "name": "",
                    "schema_version": "",
                    "active": row.id == active_pack_uuid,
                    "load_error": "Pack failed to load",
                }
            )
    return {"packs": packs}
