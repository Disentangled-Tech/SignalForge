"""Normalize RawEvent to SignalEvent data + CompanyCreate (Issue #89)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.ingestion.event_types import SIGNAL_EVENT_TYPES
from app.schemas.company import CompanyCreate, CompanySource
from app.schemas.signal import RawEvent

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE: float = 0.7


def _is_valid_event_type_for_pack(candidate: str, pack: Pack | None) -> bool:
    """Return True if candidate is valid.

    Core types (SIGNAL_EVENT_TYPES) are always accepted regardless of pack taxonomy.
    When pack is provided, pack taxonomy types are also accepted.
    When pack is None, uses is_valid_event_type (core types only).
    """
    if candidate in SIGNAL_EVENT_TYPES:
    Core types (event_types) are always accepted regardless of pack.
    When pack is provided, pack taxonomy types are also accepted.
    """
    if is_valid_event_type(candidate):
        return True
    if pack is not None:
        ids = pack.taxonomy.get("signal_ids") if isinstance(pack.taxonomy, dict) else []
        return candidate in (ids if isinstance(ids, (list, set, frozenset)) else [])
    return False


def _build_website_url(raw: RawEvent) -> str | None:
    """Build website_url from domain, website_url, or company_profile_url."""
    if raw.website_url and raw.website_url.strip():
        return raw.website_url.strip()
    if raw.domain and raw.domain.strip():
        domain = raw.domain.strip().lower()
        if not domain.startswith("http"):
            return f"https://{domain}"
        return domain
    if raw.company_profile_url and raw.company_profile_url.strip():
        url = raw.company_profile_url.strip()
        if "linkedin.com" in url.lower():
            return None
        return url
    return None


def _is_linkedin_url(url: str | None) -> bool:
    """Return True if url looks like a LinkedIn company/profile URL."""
    if not url or not url.strip():
        return False
    return "linkedin.com" in url.strip().lower()


def _extract_linkedin_url(raw: RawEvent) -> str | None:
    """Extract LinkedIn URL from company_profile_url or website_url if applicable."""
    for u in (raw.company_profile_url, raw.website_url):
        if u and _is_linkedin_url(u):
            return u.strip()
    return None


def normalize_raw_event(
    raw: RawEvent, source: str, pack: Pack | None = None
) -> tuple[dict[str, Any], CompanyCreate] | None:
    """Normalize RawEvent to (signal_event_data, company_create).

    Returns None if event_type_candidate is not in the canonical taxonomy.
    When pack is provided, validates against pack.taxonomy.signal_ids;
    otherwise uses event_types.is_valid_event_type (Phase 2, Step 3.3).
    Caller resolves company and stores the event.
    """
    if not _is_valid_event_type_for_pack(raw.event_type_candidate, pack):
        logger.debug(
            "Skipping raw event: unknown event_type_candidate=%s",
            raw.event_type_candidate,
        )
        return None

    website_url = _build_website_url(raw)
    linkedin_url = _extract_linkedin_url(raw)

    company_create = CompanyCreate(
        company_name=raw.company_name.strip(),
        website_url=website_url,
        company_linkedin_url=linkedin_url,
        source=CompanySource.research,
    )

    event_data: dict[str, Any] = {
        "source": source,
        "source_event_id": raw.source_event_id.strip() if raw.source_event_id else None,
        "event_type": raw.event_type_candidate,
        "event_time": raw.event_time,
        "title": raw.title.strip() if raw.title else None,
        "summary": raw.summary.strip() if raw.summary else None,
        "url": raw.url.strip() if raw.url else None,
        "raw": raw.raw_payload,
        "confidence": DEFAULT_CONFIDENCE,
    }

    return (event_data, company_create)
