"""Tests for scout source allowlist/denylist."""

from __future__ import annotations

from app.scout.sources import filter_allowed_sources, is_source_allowed

# ── is_source_allowed: denylist ────────────────────────────────────────────


def test_denylisted_domain_blocked() -> None:
    """URL or domain that appears in denylist is not allowed."""
    assert is_source_allowed("https://evil.com/path", [], ["evil.com"]) is False
    assert is_source_allowed("https://evil.com", [], ["evil.com"]) is False
    assert is_source_allowed("evil.com", [], ["evil.com"]) is False


def test_denylist_takes_precedence_over_allowlist() -> None:
    """If a domain is in both allowlist and denylist, it is blocked."""
    assert is_source_allowed("https://mixed.com", ["mixed.com"], ["mixed.com"]) is False


def test_not_denylisted_allowed_when_allowlist_empty() -> None:
    """When allowlist is empty, any source not on denylist is allowed."""
    assert is_source_allowed("https://example.com", [], []) is True
    assert is_source_allowed("https://news.ycombinator.com", [], []) is True
    assert is_source_allowed("https://example.com", [], ["other.com"]) is True


# ── is_source_allowed: allowlist ─────────────────────────────────────────────


def test_allowlisted_domain_allowed() -> None:
    """URL or domain that appears in allowlist is allowed (when not denylisted)."""
    assert is_source_allowed("https://good.com/page", ["good.com"], []) is True
    assert is_source_allowed("good.com", ["good.com"], []) is True


def test_non_allowlisted_domain_blocked_when_allowlist_non_empty() -> None:
    """When allowlist is non-empty, only allowlisted domains are allowed."""
    assert is_source_allowed("https://other.com", ["good.com", "allowed.org"], []) is False
    assert is_source_allowed("https://good.com", ["good.com", "allowed.org"], []) is True
    assert is_source_allowed("https://allowed.org", ["good.com", "allowed.org"], []) is True


def test_empty_allowlist_all_allowed() -> None:
    """Empty allowlist means all sources allowed (configurable default)."""
    assert is_source_allowed("https://any.com", [], []) is True
    assert is_source_allowed("https://any.com", [], ["other.com"]) is True


# ── Domain normalization ────────────────────────────────────────────────────


def test_domain_extracted_from_url() -> None:
    """Hostname is extracted from full URL for allow/deny check."""
    assert is_source_allowed("https://sub.example.com/path?q=1", [], ["sub.example.com"]) is False
    assert is_source_allowed("https://sub.example.com/path", ["sub.example.com"], []) is True


def test_case_insensitive() -> None:
    """Domain comparison is case-insensitive."""
    assert is_source_allowed("https://Example.COM", ["example.com"], []) is True
    assert is_source_allowed("https://Example.COM", [], ["EXAMPLE.com"]) is False


# ── filter_allowed_sources ──────────────────────────────────────────────────


def test_filter_allowed_sources_returns_only_allowed() -> None:
    """filter_allowed_sources returns candidates that pass allowlist/denylist, order preserved."""
    candidates = [
        "https://good.com",
        "https://blocked.com",
        "https://also-good.com",
    ]
    allowlist = ["good.com", "also-good.com"]
    denylist = ["blocked.com"]
    result = filter_allowed_sources(candidates, allowlist, denylist)
    assert result == ["https://good.com", "https://also-good.com"]


def test_filter_empty_allowlist_denylist_only() -> None:
    """With empty allowlist, filter only removes denylisted."""
    candidates = ["https://a.com", "https://b.com", "https://deny.com"]
    result = filter_allowed_sources(candidates, [], ["deny.com"])
    assert result == ["https://a.com", "https://b.com"]


def test_filter_empty_candidates() -> None:
    """Empty candidates returns empty list."""
    assert filter_allowed_sources([], ["good.com"], []) == []
