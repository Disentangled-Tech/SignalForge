"""Crunchbase ingestion adapter (Phase 1, Issue #134).

Fetches funding round events from Crunchbase API v4. Requires CRUNCHBASE_API_KEY.
When unset, returns [] and logs at debug. No exception.

Security: API key is passed in request URL (Crunchbase API design). Ensure HTTP
clients and middleware do not log full request URLs to avoid credential exposure.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from app.ingestion.base import SourceAdapter
from app.schemas.signal import RawEvent

logger = logging.getLogger(__name__)

_CRUNCHBASE_API_BASE = "https://api.crunchbase.com/v4/data/searches/funding_rounds"
_DEFAULT_LIMIT = 100


def _get_api_key() -> str | None:
    """Return CRUNCHBASE_API_KEY if set and non-empty."""
    key = os.getenv("CRUNCHBASE_API_KEY")
    return key if key and key.strip() else None


def _parse_announced_on(value: Any) -> datetime:
    """Parse announced_on value (YYYY-MM-DD) to datetime with UTC."""
    if isinstance(value, dict):
        val = value.get("value")
    else:
        val = value
    s = str(val) if val is not None else ""
    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return datetime.now(UTC)


def _entity_to_raw_event(entity: dict) -> RawEvent | None:
    """Map a Crunchbase funding round entity to RawEvent."""
    ident = entity.get("identifier") or {}
    uuid_val = ident.get("uuid") or ident.get("value") or "unknown"
    source_event_id = str(uuid_val)

    announced = entity.get("announced_on") or {}
    if isinstance(announced, dict):
        announced_val = announced.get("value")
    else:
        announced_val = announced
    event_time = _parse_announced_on(announced_val)

    org_card = entity.get("funded_organization_card") or {}
    company_name = org_card.get("name") or entity.get("funded_organization_identifier", {}).get("value") or "Unknown"
    domain = org_card.get("domain")
    homepage_url = org_card.get("homepage_url")

    money = entity.get("money_raised") or {}
    money_val = money.get("value_usd") if isinstance(money, dict) else None
    investment_type = entity.get("investment_type")
    if isinstance(investment_type, dict):
        investment_type = investment_type.get("value", "funding")
    inv_str = str(investment_type) if investment_type else "funding"
    title = f"{inv_str.replace('_', ' ').title()}"

    summary = None
    if money_val is not None:
        try:
            amount = int(money_val)
            if amount >= 1_000_000:
                summary = f"Raised ${amount / 1_000_000:.1f}M"
            else:
                summary = f"Raised ${amount:,}"
        except (TypeError, ValueError):
            pass

    return RawEvent(
        company_name=company_name.strip()[:255] if company_name else "Unknown",
        domain=str(domain)[:255] if domain else None,
        website_url=str(homepage_url)[:2048] if homepage_url else None,
        company_profile_url=None,
        event_type_candidate="funding_raised",
        event_time=event_time,
        title=title[:512] if title else None,
        summary=summary,
        url=f"https://www.crunchbase.com/funding_round/{source_event_id}" if source_event_id != "unknown" else None,
        source_event_id=source_event_id[:255],
        raw_payload={
            "money_raised": money_val,
            "investment_type": inv_str,
        },
    )


def _build_request_body(since: datetime, after_id: str | None = None) -> dict:
    """Build Crunchbase API v4 search request body."""
    since_str = since.strftime("%Y-%m-%d")
    query = [
        {
            "type": "predicate",
            "field_id": "announced_on",
            "operator_id": "gte",
            "values": [since_str],
        },
    ]
    body: dict[str, Any] = {
        "field_ids": [
            "identifier",
            "announced_on",
            "funded_organization_identifier",
            "money_raised",
            "investment_type",
        ],
        "order": [{"field_id": "announced_on", "sort": "asc"}],
        "query": query,
        "limit": _DEFAULT_LIMIT,
    }
    if after_id:
        body["after_id"] = after_id
    return body


def _fetch_page(
    client: httpx.Client,
    api_key: str,
    since: datetime,
    after_id: str | None = None,
) -> tuple[list[dict], int]:
    """Fetch one page of funding rounds. Returns (entities, status_code)."""
    url = f"{_CRUNCHBASE_API_BASE}?user_key={api_key}"
    body = _build_request_body(since, after_id)
    response = client.post(url, json=body, timeout=30.0)
    if response.status_code != 200:
        return [], response.status_code
    data = response.json()
    props = data.get("properties") or data
    entities = props.get("entities") or []
    return entities, response.status_code


class CrunchbaseAdapter(SourceAdapter):
    """Adapter for Crunchbase funding round events.

    Fetches funding rounds via Crunchbase API v4 search. Maps to RawEvent
    with event_type_candidate='funding_raised'. Returns [] when
    CRUNCHBASE_API_KEY is unset.
    """

    @property
    def source_name(self) -> str:
        return "crunchbase"

    def fetch_events(self, since: datetime) -> list[RawEvent]:
        """Fetch funding round events since given datetime."""
        api_key = _get_api_key()
        if not api_key:
            logger.debug("CRUNCHBASE_API_KEY unset – skipping Crunchbase fetch")
            return []

        events: list[RawEvent] = []
        seen_ids: set[str] = set()
        after_id: str | None = None

        with httpx.Client() as client:
            while True:
                entities, status_code = _fetch_page(client, api_key, since, after_id)

                if status_code == 429:
                    logger.warning("Crunchbase API rate limited (429) – returning partial results")
                    break

                if status_code != 200:
                    logger.warning("Crunchbase API returned %s – stopping", status_code)
                    break

                for entity in entities:
                    raw = _entity_to_raw_event(entity)
                    if raw and raw.source_event_id and raw.source_event_id not in seen_ids:
                        seen_ids.add(raw.source_event_id)
                        events.append(raw)

                if len(entities) < _DEFAULT_LIMIT:
                    break

                last = entities[-1] if entities else {}
                ident = last.get("identifier") or {}
                after_id = ident.get("uuid") or ident.get("value")
                if not after_id:
                    break

        return events
