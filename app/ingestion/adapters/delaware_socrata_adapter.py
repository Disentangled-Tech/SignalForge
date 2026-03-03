"""Delaware Socrata ingestion adapter (Issue #250, Phase 1).

Fetches incorporation filings from Delaware Open Data (Socrata SODA API).
Emits RawEvents with event_type_candidate='incorporation'. No API key required
for public datasets. When INGEST_DELAWARE_SOCRATA_DATASET_ID is unset,
returns [] and logs at debug. No exception.

Config: INGEST_DELAWARE_SOCRATA_DATASET_ID (required when enabled).
Supports flexible field mapping for entity name and file date.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.ingestion.base import SourceAdapter
from app.schemas.signal import RawEvent

logger = logging.getLogger(__name__)

_DELAWARE_SOCRATA_BASE = "https://data.delaware.gov"
_DEFAULT_PAGE_SIZE = 1000
_RETRY_429_ATTEMPTS = 3
_RETRY_429_BACKOFF_SECS = (60, 120, 300)

# Field names to try for entity name and date (dataset schemas vary)
_ENTITY_NAME_KEYS = ("entity_name", "entityname", "company_name", "name", "restname")
_DATE_KEYS = ("file_date", "filedate", "insp_date", "created_at", "date")


def _get_dataset_id() -> str | None:
    """Return INGEST_DELAWARE_SOCRATA_DATASET_ID if set and non-empty."""
    val = os.getenv("INGEST_DELAWARE_SOCRATA_DATASET_ID", "").strip()
    return val if val else None


# SoQL column names: alphanumeric and underscore only (prevents injection)
_VALID_DATE_COLUMN_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def _get_date_column() -> str | None:
    """Return date column for $where filter, or None to filter client-side.

    Validates INGEST_DELAWARE_SOCRATA_DATE_COLUMN to prevent SoQL injection.
    Only alphanumeric and underscore allowed; invalid values fall back to None.
    """
    val = os.getenv("INGEST_DELAWARE_SOCRATA_DATE_COLUMN", "file_date").strip()
    if not val:
        return None
    if _VALID_DATE_COLUMN_RE.match(val):
        return val
    logger.warning(
        "INGEST_DELAWARE_SOCRATA_DATE_COLUMN contains invalid chars (use alphanumeric, underscore only): %s",
        val[:50],
    )
    return None


def _parse_date(value: Any) -> datetime:
    """Parse SODA date/datetime to datetime with UTC."""
    s = str(value).strip() if value is not None else ""
    if not s:
        return datetime.now(UTC)
    try:
        # Handle ISO 8601 with or without time
        s = s.replace("Z", "+00:00").replace("z", "+00:00")
        if "T" in s:
            parsed = datetime.fromisoformat(s[:26])
        else:
            parsed = datetime.fromisoformat(s[:10] + "T00:00:00+00:00")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except (ValueError, TypeError):
        return datetime.now(UTC)


def _get_field(row: dict, keys: tuple[str, ...]) -> str | None:
    """Return first non-empty value for given keys (case-insensitive)."""
    row_lower = {k.lower(): v for k, v in row.items()} if isinstance(row, dict) else {}
    for key in keys:
        for k, v in row_lower.items():
            if k == key.lower() and v is not None and str(v).strip():
                return str(v).strip()
    return None


def _source_event_id(row: dict, dataset_id: str) -> str:
    """Generate stable source_event_id from row content (max 255 chars). Deduplicates identical rows."""
    entity = _get_field(row, _ENTITY_NAME_KEYS) or "unknown"
    date_val = _get_field(row, _DATE_KEYS) or ""
    entity_type = _get_field(row, ("entity_type", "entitytype", "type")) or ""
    raw = f"{dataset_id}:{entity}:{date_val}:{entity_type}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:48]
    return f"{dataset_id}:{digest}"[:255]


def _row_to_raw_event(row: dict, dataset_id: str) -> RawEvent | None:
    """Map a SODA row to RawEvent."""
    company_name = _get_field(row, _ENTITY_NAME_KEYS)
    if not company_name or len(company_name) > 255:
        company_name = company_name[:255] if company_name else "Unknown"

    date_val = _get_field(row, _DATE_KEYS)
    event_time = _parse_date(date_val) if date_val else datetime.now(UTC)

    source_event_id = _source_event_id(row, dataset_id)

    # Build title from entity type if available
    entity_type = _get_field(row, ("entity_type", "entitytype", "type"))
    title = f"Incorporation: {company_name}"
    if entity_type:
        title = f"{entity_type} formation: {company_name}"
    title = title[:512]

    url = f"{_DELAWARE_SOCRATA_BASE}/resource/{dataset_id}.json"

    return RawEvent(
        company_name=company_name,
        domain=None,
        website_url=None,
        company_profile_url=None,
        event_type_candidate="incorporation",
        event_time=event_time,
        title=title,
        summary=entity_type,
        url=url[:2048] if url else None,
        source_event_id=source_event_id,
        raw_payload={
            "entity_type": entity_type,
            "dataset_id": dataset_id,
        },
    )


def _fetch_page(
    client: httpx.Client,
    dataset_id: str,
    since: datetime,
    offset: int,
    date_column: str | None = None,
) -> tuple[list[dict], int]:
    """Fetch one page of SODA results. Returns (rows, status_code)."""
    url = f"{_DELAWARE_SOCRATA_BASE}/resource/{dataset_id}.json"
    since_str = since.strftime("%Y-%m-%d")
    params: dict[str, str | int] = {
        "$limit": _DEFAULT_PAGE_SIZE,
        "$offset": offset,
    }
    if date_column:
        params["$where"] = f"{date_column} >= '{since_str}'"

    for attempt in range(_RETRY_429_ATTEMPTS):
        try:
            response = client.get(url, params=params, timeout=30.0)
            if response.status_code == 429 and attempt < _RETRY_429_ATTEMPTS - 1:
                backoff = _RETRY_429_BACKOFF_SECS[min(attempt, len(_RETRY_429_BACKOFF_SECS) - 1)]
                logger.warning("Delaware Socrata 429 – retrying in %ds", backoff)
                time.sleep(backoff)
                continue
            if response.status_code != 200:
                return [], response.status_code
            data = response.json()
            if not isinstance(data, list):
                return [], 500
            return data, 200
        except Exception as exc:
            logger.warning("Delaware Socrata request failed: %s", exc)
            return [], 500
    return [], 500


class DelawareSocrataAdapter(SourceAdapter):
    """Adapter for Delaware Open Data (Socrata) incorporation filings.

    Fetches rows via SODA API. Maps to RawEvent with
    event_type_candidate='incorporation'. Returns [] when
    INGEST_DELAWARE_SOCRATA_DATASET_ID is unset.
    """

    @property
    def source_name(self) -> str:
        return "delaware_socrata"

    def fetch_events(self, since: datetime) -> list[RawEvent]:
        """Fetch incorporation filings since given datetime."""
        dataset_id = _get_dataset_id()
        if not dataset_id:
            logger.debug(
                "INGEST_DELAWARE_SOCRATA_DATASET_ID unset – skipping Delaware Socrata fetch"
            )
            return []

        events: list[RawEvent] = []
        seen_ids: set[str] = set()
        offset = 0
        date_column = _get_date_column()

        with httpx.Client() as client:
            while True:
                rows, status = _fetch_page(
                    client, dataset_id, since, offset, date_column=date_column
                )
                # 400 may indicate invalid $where column; retry once without filter
                if status == 400 and date_column and offset == 0:
                    date_column = None
                    rows, status = _fetch_page(client, dataset_id, since, offset, date_column=None)

                if status in (400, 401, 403, 404, 429, 500):
                    if status == 404:
                        logger.debug("Dataset not found: %s", dataset_id[:50])
                    else:
                        logger.warning("Delaware Socrata returned %s", status)
                    break

                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    raw = _row_to_raw_event(row, dataset_id)
                    if (
                        raw
                        and raw.source_event_id
                        and raw.source_event_id not in seen_ids
                        and raw.event_time >= since
                    ):
                        seen_ids.add(raw.source_event_id)
                        events.append(raw)

                if len(rows) < _DEFAULT_PAGE_SIZE:
                    break
                offset += _DEFAULT_PAGE_SIZE

        return events
