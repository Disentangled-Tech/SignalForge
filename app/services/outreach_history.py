"""Outreach history service for manual outreach tracking."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.briefing_item import BriefingItem
from app.models.outreach_history import OutreachHistory


def create_outreach_record(
    db: Session,
    company_id: int,
    sent_at: datetime,
    outreach_type: str,
    message: str | None = None,
    notes: str | None = None,
) -> OutreachHistory:
    """Insert an outreach record for a company."""
    record = OutreachHistory(
        company_id=company_id,
        outreach_type=outreach_type,
        sent_at=sent_at,
        message=message or None,
        notes=notes or None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_draft_for_company(db: Session, company_id: int) -> str | None:
    """Return the latest BriefingItem.outreach_message for pre-fill, or None."""
    item = (
        db.query(BriefingItem)
        .filter(BriefingItem.company_id == company_id)
        .order_by(BriefingItem.created_at.desc())
        .first()
    )
    return item.outreach_message if item and item.outreach_message else None


def list_outreach_for_company(
    db: Session, company_id: int
) -> list[OutreachHistory]:
    """List outreach records for a company, ordered by sent_at desc."""
    return (
        db.query(OutreachHistory)
        .filter(OutreachHistory.company_id == company_id)
        .order_by(OutreachHistory.sent_at.desc())
        .all()
    )


def delete_outreach_record(
    db: Session, company_id: int, outreach_id: int
) -> bool:
    """Delete an outreach record. Returns True if deleted, False if not found."""
    record = (
        db.query(OutreachHistory)
        .filter(
            OutreachHistory.id == outreach_id,
            OutreachHistory.company_id == company_id,
        )
        .first()
    )
    if record is None:
        return False
    db.delete(record)
    db.commit()
    return True
