"""Tests for the robots.txt parsing and can_fetch service (M1: robots-aware fetcher)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.services import robots as robots_module

# ---------------------------------------------------------------------------
# Tests: can_fetch when robots.txt allows or disallows
# ---------------------------------------------------------------------------


class TestCanFetchAllowed:
    """When robots.txt allows the path, can_fetch returns True."""

    async def test_empty_robots_allows_all(self):
        """Empty or minimal robots.txt allows all."""

        async def get(_url: str) -> str | None:
            return ""

        result = await robots_module.can_fetch(
            "https://example.com/blog",
            "SignalForge/0.1",
            _http_get=get,
        )
        assert result is True

    async def test_allow_all_explicit(self):
        """User-agent: * with no Disallow allows all."""

        async def get(_url: str) -> str | None:
            return "User-agent: *\n\n"

        result = await robots_module.can_fetch(
            "https://example.com/any/path",
            "SignalForge/0.1",
            _http_get=get,
        )
        assert result is True

    async def test_disallow_other_path_allows_this(self):
        """Disallow /admin allows /blog."""

        async def get(_url: str) -> str | None:
            return "User-agent: *\nDisallow: /admin\n"

        result = await robots_module.can_fetch(
            "https://example.com/blog",
            "SignalForge/0.1",
            _http_get=get,
        )
        assert result is True


class TestCanFetchDisallowed:
    """When robots.txt disallows the path, can_fetch returns False."""

    async def test_disallow_all(self):
        """Disallow: / disallows every path."""
        robots_module.clear_robots_cache()

        async def get(_url: str) -> str | None:
            return "User-agent: *\nDisallow: /\n"

        result = await robots_module.can_fetch(
            "https://example.com/blog",
            "SignalForge/0.1",
            _http_get=get,
        )
        assert result is False

    async def test_disallow_specific_path(self):
        """Disallow: /blog disallows /blog and subpaths."""
        robots_module.clear_robots_cache()

        async def get(_url: str) -> str | None:
            return "User-agent: *\nDisallow: /blog\n"

        result = await robots_module.can_fetch(
            "https://example.com/blog",
            "SignalForge/0.1",
            _http_get=get,
        )
        assert result is False

    async def test_disallow_for_our_user_agent(self):
        """Rules for a specific user-agent block are respected (parser matches by prefix)."""
        robots_module.clear_robots_cache()

        async def get(_url: str) -> str | None:
            # RobotFileParser applies entry if directive agent is in request's first token
            return "User-agent: SignalForge\nDisallow: /careers\n"

        result = await robots_module.can_fetch(
            "https://example.com/careers",
            "SignalForge/0.1",
            _http_get=get,
        )
        assert result is False


class TestCanFetchWhenRobotsUnavailable:
    """When robots.txt cannot be fetched (404, timeout, error), allow by convention."""

    async def test_robots_404_returns_true(self):
        """404 on robots.txt -> allow fetch (convention)."""

        async def get(_url: str) -> str | None:
            return None

        result = await robots_module.can_fetch(
            "https://example.com/blog",
            "SignalForge/0.1",
            _http_get=get,
        )
        assert result is True

    async def test_robots_fetch_raises_returns_true(self):
        """Exception during fetch -> allow (convention)."""

        async def get(_url: str) -> str | None:
            raise OSError("network error")

        result = await robots_module.can_fetch(
            "https://example.com/blog",
            "SignalForge/0.1",
            _http_get=get,
        )
        assert result is True


class TestCanFetchCaching:
    """Robots.txt is cached per origin to avoid repeated fetches."""

    async def test_same_origin_calls_http_get_once(self):
        """Second can_fetch for same origin uses cache (single _http_get call)."""
        robots_module.clear_robots_cache()
        call_count = 0

        async def get(url: str) -> str | None:
            nonlocal call_count
            call_count += 1
            assert "robots.txt" in url
            return "User-agent: *\nDisallow: /admin\n"

        result1 = await robots_module.can_fetch(
            "https://example.com/blog",
            "SignalForge/0.1",
            _http_get=get,
        )
        result2 = await robots_module.can_fetch(
            "https://example.com/news",
            "SignalForge/0.1",
            _http_get=get,
        )
        assert result1 is True
        assert result2 is True
        assert call_count == 1

    async def test_different_origins_fetch_separately(self):
        """Different origins each fetch their own robots.txt."""
        robots_module.clear_robots_cache()
        calls: list[str] = []

        async def get(url: str) -> str | None:
            calls.append(url)
            return "User-agent: *\nDisallow: /\n"

        await robots_module.can_fetch(
            "https://example.com/page",
            "SignalForge/0.1",
            _http_get=get,
        )
        await robots_module.can_fetch(
            "https://other.com/page",
            "SignalForge/0.1",
            _http_get=get,
        )
        assert len(calls) == 2
        assert any("example.com" in u for u in calls)
        assert any("other.com" in u for u in calls)


class TestCanFetchWithoutInjector:
    """When _http_get is not passed, can_fetch uses httpx (real HTTP path)."""

    async def test_can_fetch_uses_httpx_when_no_injector(self):
        """Without _http_get, module fetches robots.txt via httpx; allow by status 200."""
        robots_module.clear_robots_cache()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /admin\n"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await robots_module.can_fetch(
                "https://example.com/blog",
                "SignalForge/0.1",
            )
        assert result is True
        mock_client.get.assert_called_once()

    async def test_can_fetch_httpx_exception_returns_true(self):
        """When _http_get is not used and httpx raises, allow by convention."""
        import httpx as httpx_module

        robots_module.clear_robots_cache()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx_module.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await robots_module.can_fetch(
                "https://example.com/blog",
                "SignalForge/0.1",
            )
        assert result is True

    async def test_can_fetch_parse_exception_returns_true(self):
        """If parsing robots.txt raises, allow by convention."""
        robots_module.clear_robots_cache()

        async def get(_url: str) -> str | None:
            return "User-agent: *\nDisallow: /\n"

        with patch(
            "app.services.robots.RobotFileParser.parse",
            side_effect=ValueError("bad format"),
        ):
            result = await robots_module.can_fetch(
                "https://example.com/any",
                "SignalForge/0.1",
                _http_get=get,
            )
        assert result is True

    async def test_cache_evicts_oldest_when_over_max_entries(self):
        """When cache exceeds _ROBOTS_CACHE_MAX_ENTRIES, oldest entries are evicted."""
        robots_module.clear_robots_cache()
        calls: list[str] = []

        async def get(url: str) -> str | None:
            calls.append(url)
            return "User-agent: *\nDisallow: /admin\n"

        with patch("app.services.robots._ROBOTS_CACHE_MAX_ENTRIES", 2):
            await robots_module.can_fetch(
                "https://origin-a.com/page",
                "SignalForge/0.1",
                _http_get=get,
            )
            await robots_module.can_fetch(
                "https://origin-b.com/page",
                "SignalForge/0.1",
                _http_get=get,
            )
            await robots_module.can_fetch(
                "https://origin-c.com/page",
                "SignalForge/0.1",
                _http_get=get,
            )
            assert len(robots_module._robots_cache) <= 2
            # First origin was evicted when third was added; refetch on next access
            await robots_module.can_fetch(
                "https://origin-a.com/other",
                "SignalForge/0.1",
                _http_get=get,
            )
            assert len(calls) == 4


class TestOriginFromUrl:
    """Origin extraction for cache key and robots URL."""

    def test_https_origin(self):
        """https://example.com/path -> https://example.com."""
        from app.services.robots import _origin_from_url

        assert _origin_from_url("https://example.com/blog") == "https://example.com"

    def test_http_origin(self):
        """http://example.com -> http://example.com."""
        from app.services.robots import _origin_from_url

        assert _origin_from_url("http://example.com:8080/path") == "http://example.com:8080"

    def test_trailing_slash_stripped_from_path_only(self):
        """Origin does not include path or trailing slash."""
        from app.services.robots import _origin_from_url

        assert _origin_from_url("https://example.com/") == "https://example.com"
