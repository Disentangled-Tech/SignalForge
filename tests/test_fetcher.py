"""Tests for the HTTP page fetcher service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.fetcher import USER_AGENT, fetch_page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(text: str = "<html>OK</html>", status_code: int = 200) -> httpx.Response:
    """Create a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        text=text,
        request=httpx.Request("GET", "https://example.com"),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFetchPageSuccess:
    async def test_returns_html_on_success(self):
        mock_resp = _mock_response("<html><body>Hello</body></html>")
        with patch("app.services.fetcher.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await fetch_page("https://example.com")
            assert result == "<html><body>Hello</body></html>"

    async def test_sends_user_agent_header(self):
        mock_resp = _mock_response()
        with patch("app.services.fetcher.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await fetch_page("https://example.com")
            MockClient.assert_called_once()
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["headers"]["User-Agent"] == USER_AGENT


class TestFetchPageTimeout:
    async def test_retries_on_timeout_then_succeeds(self):
        mock_resp = _mock_response("<html>OK</html>")
        with patch("app.services.fetcher.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.side_effect = [httpx.ReadTimeout("timeout"), mock_resp]
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await fetch_page("https://slow.example.com")
            assert result == "<html>OK</html>"

    async def test_returns_none_after_two_timeouts(self):
        with patch("app.services.fetcher.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.side_effect = httpx.ReadTimeout("timeout")
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await fetch_page("https://slow.example.com")
            assert result is None


class TestFetchPageConnectionError:
    async def test_retries_on_connect_error(self):
        mock_resp = _mock_response("<html>OK</html>")
        with patch("app.services.fetcher.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.side_effect = [httpx.ConnectError("refused"), mock_resp]
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await fetch_page("https://down.example.com")
            assert result == "<html>OK</html>"

    async def test_returns_none_on_persistent_connect_error(self):
        with patch("app.services.fetcher.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.side_effect = httpx.ConnectError("refused")
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await fetch_page("https://down.example.com")
            assert result is None


class TestFetchPageHTTPError:
    async def test_returns_none_on_404(self):
        resp_404 = httpx.Response(
            status_code=404,
            request=httpx.Request("GET", "https://example.com/nope"),
        )
        with patch("app.services.fetcher.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = resp_404
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await fetch_page("https://example.com/nope")
            assert result is None


class TestFetchPageRedirect:
    async def test_follows_redirects(self):
        """Verify that follow_redirects=True is passed to the client."""
        mock_resp = _mock_response("<html>Redirected</html>")
        with patch("app.services.fetcher.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await fetch_page("https://example.com/old")
            assert result == "<html>Redirected</html>"
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["follow_redirects"] is True
            assert call_kwargs["max_redirects"] == 3

