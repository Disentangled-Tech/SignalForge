"""Signal deduplication and storage service."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.signal_record import SignalRecord

logger = logging.getLogger(__name__)

VALID_SOURCE_TYPES = frozenset(
    {"homepage", "blog", "jobs", "careers", "news", "about", "manual"}
)


def _compute_hash(content_text: str) -> str:
    """Compute SHA-256 hex digest of content_text."""
    return hashlib.sha256(content_text.encode("utf-8")).hexdigest()


def store_signal(
    db: Session,
    company_id: int,
    source_url: str,
    source_type: str,
    content_text: str,
    raw_html: str | None = None,
) -> SignalRecord | None:
    """Store a signal record with deduplication.

    Computes SHA-256 hash of *content_text*. If a SignalRecord with the same
    ``company_id`` + ``content_hash`` already exists the duplicate is skipped
    and ``None`` is returned.

    On success the parent company's ``last_scan_at`` is updated to now.

    Parameters
    ----------
    db : Session
        SQLAlchemy session (caller manages transaction boundaries).
    company_id : int
        FK to companies.id.
    source_url : str
        URL the content was fetched from.
    source_type : str
        One of: homepage, blog, jobs, careers, news, about, manual.
    content_text : str
        Extracted page text.
    raw_html : str | None, optional
        Raw HTML from the page; stored when provided.

    Returns
    -------
    SignalRecord | None
        The newly created record, or ``None`` if it was a duplicate.
    """
    content_hash = _compute_hash(content_text)

    # Dedup check: same company + same content hash → skip
    existing = (
        db.query(SignalRecord)
        .filter(
            SignalRecord.company_id == company_id,
            SignalRecord.content_hash == content_hash,
        )
        .first()
    )
    if existing is not None:
        logger.debug(
            "Duplicate signal skipped: company_id=%s hash=%s",
            company_id,
            content_hash,
        )
        # AC #14: Last activity timestamp updates — even for duplicates
        company = db.query(Company).filter(Company.id == company_id).first()
        if company is not None:
            company.last_scan_at = datetime.now(UTC)
            db.commit()
        return None

    record = SignalRecord(
        company_id=company_id,
        source_url=source_url,
        source_type=source_type,
        content_hash=content_hash,
        content_text=content_text,
        raw_html=raw_html,
    )
    db.add(record)

    # Update company.last_scan_at
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is not None:
        company.last_scan_at = datetime.now(UTC)

    db.commit()
    db.refresh(record)
    return record

