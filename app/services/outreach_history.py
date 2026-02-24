"""Outreach history service for manual outreach tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.briefing_item import BriefingItem
from app.models.outreach_history import OutreachHistory
from app.services.esl.esl_constants import (
    CADENCE_COOLDOWN_DAYS,
    DECLINED_COOLDOWN_DAYS,
)


class OutreachCooldownBlockedError(Exception):
    """Raised when cooldown or declined rule blocks new outreach record (Issue #109)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class CooldownResult:
    """Result of outreach cooldown check."""

    allowed: bool
    reason: str | None


def check_outreach_cooldown(
    db: Session,
    company_id: int,
    as_of: datetime,
) -> CooldownResult:
    """Check if new outreach is allowed per 60-day cooldown and 180-day declined rules.

    Args:
        db: Database session.
        company_id: Company to check.
        as_of: Reference datetime (typically sent_at of the new record).

    Returns:
        CooldownResult with allowed=False if blocked, reason explaining why.
    """
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)

    # 1. Check last outreach (60-day cooldown)
    last_outreach = (
        db.query(OutreachHistory.sent_at)
        .filter(OutreachHistory.company_id == company_id)
        .order_by(OutreachHistory.sent_at.desc())
        .limit(1)
        .scalar()
    )
    if last_outreach is not None:
        if last_outreach.tzinfo is None:
            last_outreach = last_outreach.replace(tzinfo=UTC)
        cutoff = as_of - timedelta(days=CADENCE_COOLDOWN_DAYS)
        if last_outreach > cutoff:
            days_ago = (as_of - last_outreach).days
            return CooldownResult(
                allowed=False,
                reason=f"Last outreach was {days_ago} days ago. Wait until 60 days have passed.",
            )

    # 2. Check declined within 180 days
    declined_cutoff = as_of - timedelta(days=DECLINED_COOLDOWN_DAYS)
    declined_exists = (
        db.query(OutreachHistory.id)
        .filter(
            OutreachHistory.company_id == company_id,
            OutreachHistory.outcome == "declined",
            OutreachHistory.sent_at > declined_cutoff,
        )
        .limit(1)
        .scalar()
    )
    if declined_exists is not None:
        return CooldownResult(
            allowed=False,
            reason="Company declined within the last 180 days.",
        )

    return CooldownResult(allowed=True, reason=None)


def create_outreach_record(
    db: Session,
    company_id: int,
    sent_at: datetime,
    outreach_type: str,
    message: str | None = None,
    notes: str | None = None,
    outcome: str | None = None,
    workspace_id: str | None = None,
) -> OutreachHistory:
    """Insert an outreach record for a company.

    Enforces 60-day cooldown and 180-day declined rules (Issue #109).
    Raises OutreachCooldownBlockedError if blocked.
    When workspace_id is provided, associates outreach with that workspace for
    multi-tenant scoping. When None, uses default workspace (backward compat).
    """
    from uuid import UUID

    from app.pipeline.stages import DEFAULT_WORKSPACE_ID

    result = check_outreach_cooldown(db, company_id, sent_at)
    if not result.allowed:
        raise OutreachCooldownBlockedError(result.reason or "Outreach blocked.")

    ws_uuid = (
        UUID(str(workspace_id))
        if workspace_id is not None
        else UUID(DEFAULT_WORKSPACE_ID)
    )

    record = OutreachHistory(
        company_id=company_id,
        outreach_type=outreach_type,
        sent_at=sent_at,
        message=message or None,
        notes=notes or None,
        outcome=outcome or None,
        workspace_id=ws_uuid,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    # Refresh lead_feed outreach_status_summary (Phase 3, Issue #225)
    from app.services.lead_feed import refresh_outreach_summary_for_entity

    refresh_outreach_summary_for_entity(db, company_id, workspace_id=ws_uuid)
    db.commit()
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


def update_outreach_outcome(
    db: Session,
    company_id: int,
    outreach_id: int,
    outcome: str | None,
) -> OutreachHistory | None:
    """Update the outcome of an existing outreach record. Returns None if not found.

    outcome=None or empty string clears the outcome.
    """
    record = (
        db.query(OutreachHistory)
        .filter(
            OutreachHistory.id == outreach_id,
            OutreachHistory.company_id == company_id,
        )
        .first()
    )
    if record is None:
        return None
    record.outcome = outcome if outcome else None
    db.commit()
    db.refresh(record)
    # Refresh lead_feed outreach_status_summary (Phase 3, Issue #225)
    from app.services.lead_feed import refresh_outreach_summary_for_entity

    refresh_outreach_summary_for_entity(
        db, company_id, workspace_id=record.workspace_id
    )
    db.commit()
    return record


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
    ws_id = record.workspace_id
    db.delete(record)
    db.commit()
    # Refresh lead_feed outreach_status_summary (Phase 3, Issue #225)
    from app.services.lead_feed import refresh_outreach_summary_for_entity

    refresh_outreach_summary_for_entity(db, company_id, workspace_id=ws_id)
    db.commit()
    return True
