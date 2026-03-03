"""NewsAPI ingestion adapter (Issue #245, Phase 1).

Fetches funding-related news articles via configurable keywords. Emits RawEvents
with event_type_candidate='funding_raised'. Requires NEWSAPI_API_KEY.
When unset, returns [] and logs at debug. No exception.

Security: API key is passed in request params. Ensure HTTP clients and
middleware do not log full request URLs to avoid credential exposure.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from app.ingestion.base import SourceAdapter
from app.schemas.signal import RawEvent

logger = logging.getLogger(__name__)

_NEWSAPI_BASE = "https://newsapi.org/v2/everything"
_DEFAULT_PAGE_SIZE = 100
_DEFAULT_KEYWORDS = [
    "series A funding",
    "raised funding",
    "seed round",
    "venture capital funding",
    "closes round",
]


def _get_api_key() -> str | None:
    """Return NEWSAPI_API_KEY if set and non-empty."""
    key = os.getenv("NEWSAPI_API_KEY")
    return key if key and key.strip() else None


def _get_keywords() -> list[str]:
    """Return configurable keyword list.

    Priority: INGEST_NEWSAPI_KEYWORDS_JSON (JSON array) >
    INGEST_NEWSAPI_KEYWORDS (comma-separated) > default list.
    """
    json_val = os.getenv("INGEST_NEWSAPI_KEYWORDS_JSON", "").strip()
    if json_val:
        try:
            arr = json.loads(json_val)
            if isinstance(arr, list):
                return [str(k).strip() for k in arr if str(k).strip()]
        except json.JSONDecodeError:
            pass
    csv_val = os.getenv("INGEST_NEWSAPI_KEYWORDS", "").strip()
    if csv_val:
        return [k.strip() for k in csv_val.split(",") if k.strip()]
    return _DEFAULT_KEYWORDS


def _extract_company_name(title: str | None, description: str | None) -> str:
    """Extract company name from article title/description (naive heuristic).

    Tries: text before 'raises', 'secures', 'announces'; first quoted phrase.
    Fallback: 'Unknown'.
    """
    text = (title or "") + " " + (description or "")
    if not text.strip():
        return "Unknown"

    # Pattern: "Acme raises $10M" or "Acme secures funding"
    for pattern in [
        r"^([^.!?]+?)\s+raises\s",
        r"^([^.!?]+?)\s+secures\s",
        r"^([^.!?]+?)\s+announces\s",
        r"^([^.!?]+?)\s+closes\s",
        r"^([^.!?]+?)\s+raised\s",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if name and len(name) <= 255:
                return name[:255]

    # First quoted phrase
    quoted = re.search(r'"([^"]+)"', text)
    if quoted:
        name = quoted.group(1).strip()
        if name and len(name) <= 255:
            return name[:255]

    return "Unknown"


def _source_event_id_from_url(url: str | None) -> str:
    """Generate stable source_event_id from URL (max 255 chars)."""
    if not url or not url.strip():
        return hashlib.sha256(b"unknown").hexdigest()[:64]
    digest = hashlib.sha256(url.strip().encode()).hexdigest()
    return digest[:64]


def _parse_published_at(value: Any) -> datetime:
    """Parse publishedAt (ISO 8601) to datetime with UTC."""
    s = str(value) if value is not None else ""
    if not s:
        return datetime.now(UTC)
    try:
        s = s.replace("Z", "+00:00").replace("z", "+00:00")
        parsed = datetime.fromisoformat(s[:26])
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except (ValueError, TypeError):
        return datetime.now(UTC)


def _article_to_raw_event(article: dict) -> RawEvent | None:
    """Map a NewsAPI article to RawEvent."""
    url = article.get("url")
    if not url or not str(url).strip():
        return None

    source_event_id = _source_event_id_from_url(url)[:255]
    title = article.get("title") or ""
    description = article.get("description") or ""
    source_name = ""
    if isinstance(article.get("source"), dict):
        source_name = article.get("source", {}).get("name") or ""

    company_name = _extract_company_name(title, description)
    if not company_name or company_name == "Unknown":
        company_name = "Unknown"

    event_time = _parse_published_at(article.get("publishedAt"))

    return RawEvent(
        company_name=company_name[:255],
        domain=None,
        website_url=None,
        company_profile_url=None,
        event_type_candidate="funding_raised",
        event_time=event_time,
        title=title[:512] if title else None,
        summary=description[:2048] if description else None,
        url=str(url)[:2048],
        source_event_id=source_event_id,
        raw_payload={
            "source_name": source_name,
            "title": title,
        },
    )


def _fetch_page(
    client: httpx.Client,
    api_key: str,
    keyword: str,
    since: datetime,
    page: int = 1,
) -> tuple[list[dict], int, int]:
    """Fetch one page of articles. Returns (articles, status_code, total_results)."""
    from_str = since.strftime("%Y-%m-%d")
    params: dict[str, str | int] = {
        "q": keyword,
        "from": from_str,
        "sortBy": "publishedAt",
        "pageSize": _DEFAULT_PAGE_SIZE,
        "page": page,
        "apiKey": api_key,
    }
    try:
        response = client.get(_NEWSAPI_BASE, params=params, timeout=30.0)
        if response.status_code != 200:
            return [], response.status_code, 0
        data = response.json()
        if data.get("status") != "ok":
            return [], 500, 0
        articles = data.get("articles") or []
        total = data.get("totalResults", 0)
        return articles, 200, total
    except Exception as exc:
        logger.warning("NewsAPI request failed: %s", exc)
        return [], 500, 0


class NewsAPIAdapter(SourceAdapter):
    """Adapter for NewsAPI funding-related news articles.

    Fetches articles via keyword queries. Maps to RawEvent with
    event_type_candidate='funding_raised'. Returns [] when
    NEWSAPI_API_KEY is unset.
    """

    @property
    def source_name(self) -> str:
        return "newsapi"

    def fetch_events(self, since: datetime) -> list[RawEvent]:
        """Fetch funding-related articles since given datetime."""
        api_key = _get_api_key()
        if not api_key:
            logger.debug("NEWSAPI_API_KEY unset – skipping NewsAPI fetch")
            return []

        keywords = _get_keywords()
        if not keywords:
            return []

        events: list[RawEvent] = []
        seen_ids: set[str] = set()

        with httpx.Client() as client:
            for keyword in keywords:
                page = 1
                while True:
                    articles, status_code, total_results = _fetch_page(
                        client, api_key, keyword, since, page
                    )

                    if status_code in (401, 403, 429, 500):
                        logger.warning(
                            "NewsAPI returned %s – stopping keyword %s",
                            status_code,
                            keyword[:20],
                        )
                        break

                    if status_code != 200:
                        break

                    for article in articles:
                        raw = _article_to_raw_event(article)
                        if raw and raw.source_event_id and raw.source_event_id not in seen_ids:
                            seen_ids.add(raw.source_event_id)
                            events.append(raw)

                    if len(articles) < _DEFAULT_PAGE_SIZE:
                        break
                    if page * _DEFAULT_PAGE_SIZE >= total_results:
                        break
                    page += 1

        return events
