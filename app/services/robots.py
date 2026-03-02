"""Robots.txt parsing and can_fetch for robots-aware fetching (M1: diff-based monitor)."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

# Cache TTL in seconds; avoid refetching robots.txt on every request
_ROBOTS_CACHE_TTL_SECONDS = 3600
# Max origins to cache; oldest (by fetched_at) evicted when over limit
_ROBOTS_CACHE_MAX_ENTRIES = 1000

# Module-level cache: origin -> (RobotFileParser, fetched_at_timestamp).
# Per-process only; not shared across worker processes.
_robots_cache: dict[str, tuple[RobotFileParser, float]] = {}


def _origin_from_url(url: str) -> str:
    """Return scheme + netloc for cache key and robots URL. No path."""
    parsed = urlparse(url)
    netloc = parsed.netloc or parsed.path.split("/")[0]
    scheme = parsed.scheme or "https"
    return f"{scheme}://{netloc}"


def clear_robots_cache() -> None:
    """Clear the per-origin robots.txt cache. Used by tests."""
    _robots_cache.clear()


def _evict_oldest_entries_if_over_capacity() -> None:
    """If cache is over _ROBOTS_CACHE_MAX_ENTRIES, evict oldest entries by fetched_at."""
    if len(_robots_cache) < _ROBOTS_CACHE_MAX_ENTRIES:
        return
    by_time = sorted(_robots_cache.items(), key=lambda x: x[1][1])
    to_remove = len(_robots_cache) - _ROBOTS_CACHE_MAX_ENTRIES + 1
    for origin, _ in by_time[:to_remove]:
        del _robots_cache[origin]


async def can_fetch(
    url: str,
    user_agent: str,
    *,
    _http_get: Callable[[str], Awaitable[str | None]] | None = None,
) -> bool:
    """Return True if user_agent is allowed to fetch url according to robots.txt.

    Fetches robots.txt from the URL's origin, parses it, and caches per origin.
    If robots.txt cannot be fetched (404, timeout, error), returns True (allow
    by convention). Cache is per-process and not shared across worker processes.
    Safe for cache reads/writes within a single event loop.
    """
    origin = _origin_from_url(url)
    now = time.time()

    if origin in _robots_cache:
        parser, fetched_at = _robots_cache[origin]
        if now - fetched_at < _ROBOTS_CACHE_TTL_SECONDS:
            return parser.can_fetch(user_agent, url)

    robots_url = f"{origin.rstrip('/')}/robots.txt"
    if _http_get is not None:
        try:
            body = await _http_get(robots_url)
        except OSError as exc:
            logger.debug(
                "robots.txt unreachable for %s: %s -> allow by convention", robots_url, exc
            )
            return True
    else:
        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                headers={"User-Agent": user_agent},
                follow_redirects=True,
                max_redirects=3,
            ) as client:
                response = await client.get(robots_url)
                if response.status_code != 200:
                    logger.debug(
                        "robots.txt %s for %s -> allow by convention",
                        response.status_code,
                        robots_url,
                    )
                    return True
                body = response.text
        except (OSError, httpx.HTTPError) as exc:
            logger.debug(
                "robots.txt unreachable for %s: %s -> allow by convention", robots_url, exc
            )
            return True

    if body is None or not body.strip():
        return True

    try:
        rp = RobotFileParser()
        rp.parse(body.splitlines())
        _evict_oldest_entries_if_over_capacity()
        _robots_cache[origin] = (rp, now)
        return rp.can_fetch(user_agent, url)
    except (ValueError, TypeError) as exc:
        logger.debug("robots.txt parse error for %s: %s -> allow by convention", robots_url, exc)
        return True
