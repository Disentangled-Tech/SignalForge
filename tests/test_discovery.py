"""Tests for the page discovery service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.page_discovery import _normalize_url, discover_pages


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------


class TestNormalizeUrl:
    def test_strips_trailing_slash(self):
        assert _normalize_url("https://example.com/") == "https://example.com"

    def test_adds_https_scheme(self):
        assert _normalize_url("example.com") == "https://example.com"

    def test_preserves_http_scheme(self):
        assert _normalize_url("http://example.com") == "http://example.com"

    def test_preserves_https_scheme(self):
        assert _normalize_url("https://example.com") == "https://example.com"

    def test_strips_whitespace(self):
        assert _normalize_url("  https://example.com  ") == "https://example.com"


# ---------------------------------------------------------------------------
# Page discovery
# ---------------------------------------------------------------------------

# Meaningful content = >100 chars
_MEANINGFUL_TEXT = "A" * 150
_SHORT_TEXT = "tiny"

_HOMEPAGE_HTML = f"<html><body><p>{_MEANINGFUL_TEXT}</p></body></html>"
_SUBPAGE_HTML = f"<html><body><p>{'B' * 200}</p></body></html>"
_SHORT_HTML = f"<html><body><p>{_SHORT_TEXT}</p></body></html>"


class TestDiscoverPages:
    async def test_discovers_homepage(self):
        with patch("app.services.page_discovery.fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _HOMEPAGE_HTML

            results = await discover_pages("https://example.com")
            assert len(results) >= 1
            assert results[0][0] == "https://example.com"
            assert len(results[0][1]) > 100
            assert results[0][2] == _HOMEPAGE_HTML

    async def test_discovers_subpages(self):
        async def _mock_fetch(url: str) -> str | None:
            return _SUBPAGE_HTML

        with patch("app.services.page_discovery.fetch_page", side_effect=_mock_fetch):
            results = await discover_pages("https://example.com")
            # Should have homepage + sub-pages (up to 5 total)
            assert len(results) > 1
            urls = [r[0] for r in results]
            assert "https://example.com" in urls
            for url, text, raw_html in results:
                assert raw_html == _SUBPAGE_HTML

    async def test_respects_max_5_limit(self):
        """Even if all paths return content, we cap at 5 pages."""
        async def _mock_fetch(url: str) -> str | None:
            return _SUBPAGE_HTML

        with patch("app.services.page_discovery.fetch_page", side_effect=_mock_fetch):
            results = await discover_pages("https://example.com")
            assert len(results) <= 5

    async def test_skips_pages_with_short_content(self):
        async def _mock_fetch(url: str) -> str | None:
            if url == "https://example.com":
                return _HOMEPAGE_HTML
            return _SHORT_HTML  # Other pages have too little text

        with patch("app.services.page_discovery.fetch_page", side_effect=_mock_fetch):
            results = await discover_pages("https://example.com")
            assert len(results) == 1  # Only homepage passes

    async def test_skips_pages_that_fail_to_fetch(self):
        call_count = 0

        async def _mock_fetch(url: str) -> str | None:
            nonlocal call_count
            call_count += 1
            if url == "https://example.com":
                return _HOMEPAGE_HTML
            return None  # All sub-pages fail

        with patch("app.services.page_discovery.fetch_page", side_effect=_mock_fetch):
            results = await discover_pages("https://example.com")
            assert len(results) == 1  # Only homepage

    async def test_handles_no_homepage(self):
        """If even the homepage fails, return empty list."""
        with patch("app.services.page_discovery.fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            results = await discover_pages("https://dead-site.example.com")
            assert results == []

    async def test_normalizes_base_url(self):
        with patch("app.services.page_discovery.fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _HOMEPAGE_HTML

            results = await discover_pages("example.com/")
            assert len(results) >= 1
            # Should have been normalized to https
            assert results[0][0].startswith("https://")

    async def test_returns_url_and_text_tuples(self):
        with patch("app.services.page_discovery.fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _HOMEPAGE_HTML

            results = await discover_pages("https://example.com")
            for url, text, raw_html in results:
                assert isinstance(url, str)
                assert isinstance(text, str)
                assert isinstance(raw_html, str) or raw_html is None
                assert url.startswith("http")

    async def test_discover_pages_returns_raw_html_in_tuples(self):
        """Each result tuple includes (url, content_text, raw_html)."""
        with patch("app.services.page_discovery.fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _HOMEPAGE_HTML

            results = await discover_pages("https://example.com")
            assert len(results) >= 1
            url, text, raw_html = results[0]
            assert url == "https://example.com"
            assert len(text) > 100
            assert raw_html == _HOMEPAGE_HTML

    async def test_tries_only_issue_13_paths(self):
        """Only /blog, /news, /careers, /jobs are tried (no /about)."""
        with patch("app.services.page_discovery.fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _SUBPAGE_HTML

            await discover_pages("https://example.com")

            call_urls = [call[0][0] for call in mock_fetch.call_args_list]
            assert "https://example.com/about" not in call_urls
            for path in ["/blog", "/news", "/careers", "/jobs"]:
                assert f"https://example.com{path}" in call_urls

    async def test_fetch_order_homepage_then_common_paths(self):
        """fetch_page is called with homepage first, then paths in COMMON_PATHS order."""
        with patch("app.services.page_discovery.fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _SUBPAGE_HTML

            await discover_pages("https://example.com")

            from app.services.page_discovery import COMMON_PATHS

            call_urls = [call[0][0] for call in mock_fetch.call_args_list]
            assert call_urls[0] == "https://example.com"
            for i, path in enumerate(COMMON_PATHS):
                expected = f"https://example.com{path}"
                assert call_urls[i + 1] == expected


# ---------------------------------------------------------------------------
# Valid page validation
# ---------------------------------------------------------------------------


class TestValidPageCriteria:
    def test_rejects_empty_html(self):
        from app.services.page_discovery import _is_valid_page

        assert _is_valid_page("", "some text") is False

    def test_rejects_short_text(self):
        from app.services.page_discovery import _is_valid_page

        assert _is_valid_page("<html>ok</html>", "x" * 50) is False

    def test_rejects_exactly_min_length_text_with_empty_html(self):
        from app.services.page_discovery import _is_valid_page, MIN_TEXT_LENGTH

        assert _is_valid_page("", "x" * MIN_TEXT_LENGTH) is False

    def test_accepts_long_text_with_non_empty_html(self):
        from app.services.page_discovery import _is_valid_page, MIN_TEXT_LENGTH

        assert _is_valid_page("<html>ok</html>", "x" * (MIN_TEXT_LENGTH + 1)) is True

