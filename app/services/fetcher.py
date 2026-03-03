"""HTTP page fetcher using httpx async client."""

from __future__ import annotations

import logging

import httpx

from app.services import robots as robots_module

logger = logging.getLogger(__name__)

USER_AGENT = "SignalForge/0.1 (startup-monitor)"
TIMEOUT = 15.0
MAX_REDIRECTS = 3


async def fetch_page(url: str, check_robots: bool = False) -> str | None:
    """Fetch a URL and return raw HTML, or None on failure.

    - When check_robots is True, consults robots.txt for the URL's origin first;
      if disallowed, returns None without fetching (no HTTP request to the page).
    - 15-second timeout
    - One retry on timeout or connection error
    - Follows up to 3 redirects
    - Logs errors but never raises
    """
    if check_robots:
        allowed = await robots_module.can_fetch(url, USER_AGENT)
        if not allowed:
            logger.debug("Robots.txt disallows %s for %s — skipping fetch", USER_AGENT, url)
            return None
    for attempt in range(2):  # attempt 0 = first try, attempt 1 = retry
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT,
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            if attempt == 0:
                logger.warning("Fetch attempt 1 failed for %s: %s — retrying", url, exc)
                continue
            logger.error("Fetch failed after retry for %s: %s", url, exc)
            return None
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP %s for %s", exc.response.status_code, url)
            return None
        except httpx.HTTPError as exc:
            logger.error("HTTP error fetching %s: %s", url, exc)
            return None
    return None
