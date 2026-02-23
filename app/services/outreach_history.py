"""Outreach history service for manual outreach tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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
        as_of = as_of.replace(tzinfo=timezone.utc)

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
            last_outreach = last_outreach.replace(tzinfo=timezone.utc)
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
    timing_quality_feedback: str | None = None,
) -> OutreachHistory:
    """Insert an outreach record for a company.

    Enforces 60-day cooldown and 180-day declined rules (Issue #109).
    Raises OutreachCooldownBlockedError if blocked.
    """
    result = check_outreach_cooldown(db, company_id, sent_at)
    if not result.allowed:
        raise OutreachCooldownBlockedError(result.reason or "Outreach blocked.")

    record = OutreachHistory(
        company_id=company_id,
        outreach_type=outreach_type,
        sent_at=sent_at,
        message=message or None,
        notes=notes or None,
        outcome=outcome or None,
        timing_quality_feedback=timing_quality_feedback or None,
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


def update_outreach_record(
    db: Session,
    company_id: int,
    outreach_id: int,
    *,
    outcome: str | None = None,
    notes: str | None = None,
    timing_quality_feedback: str | None = None,
) -> OutreachHistory | None:
    """Update outcome, notes, and/or timing_quality_feedback on an outreach record.

    PATCH semantics: None means "omit, do not update". Empty string means "clear".
    Returns None if not found.
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
    if outcome is not None:
        record.outcome = outcome.strip() if outcome else None
    if notes is not None:
        record.notes = notes.strip() if notes else None
    if timing_quality_feedback is not None:
        val = timing_quality_feedback.strip() if timing_quality_feedback else None
        record.timing_quality_feedback = val
    db.commit()
    db.refresh(record)
    return record


def update_outreach_outcome(
    db: Session,
    company_id: int,
    outreach_id: int,
    outcome: str | None,
) -> OutreachHistory | None:
    """Update the outcome of an existing outreach record. Returns None if not found.

    outcome=None or empty string clears the outcome.
    """
    # Pass "" to mean "clear" so update_outreach_record sets to null
    outcome_val = "" if outcome is None or outcome == "" else outcome
    return update_outreach_record(
        db, company_id, outreach_id, outcome=outcome_val
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
