"""Scout source allowlist/denylist — filter URLs/domains before fetching.

Used only in the Scout path. Denylist takes precedence; empty allowlist = all allowed.
"""

from __future__ import annotations

from urllib.parse import urlparse


def _domain_of(url_or_domain: str) -> str:
    """Extract hostname from URL or return normalized domain string."""
    s = url_or_domain.strip().lower()
    if "://" in s:
        parsed = urlparse(s if "://" in s else "https://" + s)
        return (parsed.netloc or s).split(":")[0]
    return s.split("/")[0].split(":")[0]


def is_source_allowed(
    url_or_domain: str,
    allowlist: list[str],
    denylist: list[str],
) -> bool:
    """Return True if the source is allowed: not denylisted, and (allowlist empty or in allowlist).

    Denylist takes precedence. Empty allowlist means all sources are allowed (subject to denylist).
    """
    domain = _domain_of(url_or_domain)
    denylist_normalized = [d.strip().lower() for d in denylist]
    if domain in denylist_normalized:
        return False
    if not allowlist:
        return True
    allowlist_normalized = [a.strip().lower() for a in allowlist]
    return domain in allowlist_normalized


def filter_allowed_sources(
    candidates: list[str],
    allowlist: list[str],
    denylist: list[str],
) -> list[str]:
    """Return only candidates that pass allowlist/denylist (order preserved)."""
    return [c for c in candidates if is_source_allowed(c, allowlist, denylist)]
