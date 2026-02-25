"""Product Hunt ingestion adapter (Phase 3, Issue #210).

Fetches product launch events from Product Hunt GraphQL API v2. Requires
PRODUCTHUNT_API_TOKEN. When unset, returns [] and logs at debug. No exception.

Security: Token is passed in Authorization header. Ensure HTTP clients and
middleware redact Authorization headers in logs to avoid credential exposure.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.ingestion.base import SourceAdapter
from app.schemas.signal import RawEvent

logger = logging.getLogger(__name__)

_PRODUCTHUNT_GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"
_DEFAULT_PAGE_SIZE = 50

_POSTS_QUERY = """
query Posts($postedAfter: DateTime!, $first: Int!, $after: String) {
  posts(postedAfter: $postedAfter, first: $first, after: $after, order: NEWEST) {
    edges {
      node {
        id
        name
        tagline
        url
        website
        createdAt
      }
      cursor
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


def _get_api_token() -> str | None:
    """Return PRODUCTHUNT_API_TOKEN if set and non-empty."""
    token = os.getenv("PRODUCTHUNT_API_TOKEN")
    return token if token and token.strip() else None


def _domain_from_url(url: str | None) -> str | None:
    """Extract domain from URL (e.g. https://acme.com/path -> acme.com)."""
    if not url or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
        netloc = parsed.netloc or parsed.path
        if not netloc:
            return None
        # Strip www. prefix
        if netloc.lower().startswith("www."):
            netloc = netloc[4:]
        return netloc[:255] if netloc else None
    except Exception:
        return None


def _parse_created_at(value: Any) -> datetime:
    """Parse createdAt (ISO 8601) to datetime with UTC."""
    s = str(value) if value is not None else ""
    if not s:
        return datetime.now(UTC)
    try:
        # Handle Z suffix and +00:00
        s = s.replace("Z", "+00:00").replace("z", "+00:00")
        parsed = datetime.fromisoformat(s[:26])  # truncate fractional seconds if long
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except (ValueError, TypeError):
        return datetime.now(UTC)


def _post_node_to_raw_event(node: dict) -> RawEvent | None:
    """Map a Product Hunt post node to RawEvent."""
    post_id = node.get("id")
    if not post_id:
        return None
    source_event_id = str(post_id)[:255]

    name = (node.get("name") or "Unknown").strip()[:255]
    tagline = (node.get("tagline") or "").strip() or None
    website = node.get("website")
    website_url = str(website)[:2048] if website else None
    ph_url = node.get("url")
    url = str(ph_url)[:2048] if ph_url else f"https://www.producthunt.com/posts/{source_event_id}"

    created_at = node.get("createdAt")
    event_time = _parse_created_at(created_at)

    domain = _domain_from_url(website_url)

    return RawEvent(
        company_name=name or "Unknown",
        domain=domain,
        website_url=website_url,
        company_profile_url=None,
        event_type_candidate="launch_major",
        event_time=event_time,
        title=name[:512] if name else None,
        summary=tagline,
        url=url,
        source_event_id=source_event_id,
        raw_payload={"votesCount": node.get("votesCount"), "tagline": tagline},
    )


def _fetch_page(
    client: httpx.Client,
    token: str,
    posted_after: str,
    after_cursor: str | None = None,
) -> tuple[list[dict], bool, str | None]:
    """Fetch one page of posts. Returns (nodes, has_next, end_cursor)."""
    variables: dict[str, Any] = {
        "postedAfter": posted_after,
        "first": _DEFAULT_PAGE_SIZE,
    }
    if after_cursor:
        variables["after"] = after_cursor

    payload = {"query": _POSTS_QUERY, "variables": variables}
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    response = client.post(
        _PRODUCTHUNT_GRAPHQL_URL,
        json=payload,
        headers=headers,
        timeout=30.0,
    )

    if response.status_code != 200:
        return [], False, None

    data = response.json()
    if "errors" in data and data["errors"]:
        logger.warning("Product Hunt GraphQL errors: %s", data["errors"][:3])
        return [], False, None

    posts_data = data.get("data", {}).get("posts") or {}
    edges = posts_data.get("edges") or []
    page_info = posts_data.get("pageInfo") or {}
    nodes = [e.get("node") for e in edges if e.get("node")]
    has_next = page_info.get("hasNextPage", False)
    end_cursor = page_info.get("endCursor")

    return nodes, has_next, end_cursor


class ProductHuntAdapter(SourceAdapter):
    """Adapter for Product Hunt product launch events.

    Fetches posts via Product Hunt GraphQL API v2. Maps to RawEvent
    with event_type_candidate='launch_major'. Returns [] when
    PRODUCTHUNT_API_TOKEN is unset.
    """

    @property
    def source_name(self) -> str:
        return "producthunt"

    def fetch_events(self, since: datetime) -> list[RawEvent]:
        """Fetch product launch events since given datetime."""
        token = _get_api_token()
        if not token:
            logger.debug("PRODUCTHUNT_API_TOKEN unset – skipping Product Hunt fetch")
            return []

        # Product Hunt API expects ISO 8601
        posted_after = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        if since.tzinfo is None:
            posted_after = since.replace(tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        events: list[RawEvent] = []
        seen_ids: set[str] = set()
        after_cursor: str | None = None

        with httpx.Client() as client:
            while True:
                nodes, has_next, end_cursor = _fetch_page(
                    client, token, posted_after, after_cursor
                )

                for node in nodes:
                    raw = _post_node_to_raw_event(node)
                    if raw and raw.source_event_id and raw.source_event_id not in seen_ids:
                        seen_ids.add(raw.source_event_id)
                        events.append(raw)

                if not has_next or not end_cursor:
                    break
                after_cursor = end_cursor

        return events
