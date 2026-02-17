"""Discover sub-pages on a company website."""

from __future__ import annotations

import logging
from urllib.parse import urljoin

from app.services.extractor import extract_text
from app.services.fetcher import fetch_page

logger = logging.getLogger(__name__)

# Common paths to check for meaningful content
_COMMON_PATHS = ["/blog", "/news", "/careers", "/jobs", "/about"]

# Minimum text length to consider a page "meaningful"
_MIN_TEXT_LENGTH = 100

# Maximum number of pages to return (homepage + sub-pages)
_MAX_PAGES = 5


def _normalize_url(url: str) -> str:
    """Normalize a base URL: strip trailing slash, ensure https://."""
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


async def discover_pages(base_url: str) -> list[tuple[str, str, str | None]]:
    """Discover pages on a company website and extract text.

    Returns a list of (url, clean_text, raw_html) tuples.
    - Tries homepage first, then common sub-paths
    - Only keeps pages with meaningful content (>100 chars)
    - Returns at most 5 pages total
    """
    base_url = _normalize_url(base_url)
    results: list[tuple[str, str, str | None]] = []

    # Try homepage first
    html = await fetch_page(base_url)
    if html:
        text = extract_text(html)
        if len(text) > _MIN_TEXT_LENGTH:
            results.append((base_url, text, html))
            logger.debug("discover_pages: %s OK (%d chars)", base_url, len(text))
        else:
            logger.debug("discover_pages: %s fetched but text too short (%d < %d)", base_url, len(text), _MIN_TEXT_LENGTH)
    else:
        logger.warning("discover_pages: %s fetch failed (timeout, connection error, or non-2xx)", base_url)

    # Try common sub-paths
    for path in _COMMON_PATHS:
        if len(results) >= _MAX_PAGES:
            break

        page_url = urljoin(base_url + "/", path.lstrip("/"))
        html = await fetch_page(page_url)
        if html:
            text = extract_text(html)
            if len(text) > _MIN_TEXT_LENGTH:
                results.append((page_url, text, html))
                logger.debug("discover_pages: %s OK (%d chars)", page_url, len(text))
        # Don't log every 404 for /blog, /news etc – many sites don't have them

    return results

