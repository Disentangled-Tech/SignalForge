"""Quarantine read interface (M4, Issue #278). List and get evidence_quarantine entries."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.evidence_quarantine import EvidenceQuarantine
from app.schemas.evidence import QuarantineEntryRead


def list_quarantine(
    db: Session,
    limit: int = 100,
    offset: int = 0,
    reason_substring: str | None = None,
    since: datetime | None = None,
) -> list[QuarantineEntryRead]:
    """Return quarantine entries, newest first. Optional filter by reason substring and since."""
    q = db.query(EvidenceQuarantine).order_by(EvidenceQuarantine.created_at.desc())
    if reason_substring is not None and reason_substring.strip():
        q = q.filter(EvidenceQuarantine.reason.ilike(f"%{reason_substring.strip()}%"))
    if since is not None:
        q = q.filter(EvidenceQuarantine.created_at >= since)
    rows = q.limit(limit).offset(offset).all()
    return [_row_to_read(r) for r in rows]


def get_quarantine(db: Session, id: uuid.UUID) -> QuarantineEntryRead | None:
    """Return one quarantine entry by id, or None if not found."""
    row = db.query(EvidenceQuarantine).filter(EvidenceQuarantine.id == id).first()
    if row is None:
        return None
    return _row_to_read(row)


def _row_to_read(row: EvidenceQuarantine) -> QuarantineEntryRead:
    reason_codes: list[str] | None = None
    if isinstance(row.payload, dict) and "reason_codes" in row.payload:
        raw = row.payload["reason_codes"]
        if isinstance(raw, list):
            reason_codes = [str(x) for x in raw]
    return QuarantineEntryRead(
        id=row.id,
        payload=row.payload,
        reason=row.reason,
        reason_codes=reason_codes,
        created_at=row.created_at,
    )
