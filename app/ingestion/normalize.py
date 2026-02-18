"""Normalize RawEvent to SignalEvent data + CompanyCreate (Issue #89)."""

from __future__ import annotations

import logging
from typing import Any

from app.schemas.company import CompanyCreate, CompanySource
from app.schemas.signal import RawEvent
from app.ingestion.event_types import is_valid_event_type

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE: float = 0.7


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


def normalize_raw_event(raw: RawEvent, source: str) -> tuple[dict[str, Any], CompanyCreate] | None:
    """Normalize RawEvent to (signal_event_data, company_create).

    Returns None if event_type_candidate is not in the canonical taxonomy.
    Caller resolves company and stores the event.
    """
    if not is_valid_event_type(raw.event_type_candidate):
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
