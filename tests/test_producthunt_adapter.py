"""Tests for Product Hunt ingestion adapter (Phase 3, Issue #210)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.ingestion.adapters.producthunt_adapter import ProductHuntAdapter
from app.ingestion.event_types import SIGNAL_EVENT_TYPES


def _make_post_node(
    *,
    post_id: str = "ph-post-1",
    name: str = "Acme Product",
    tagline: str = "Build faster",
    website: str = "https://acme.com",
    url: str = "https://www.producthunt.com/posts/acme",
    created_at: str = "2026-02-20T10:00:00Z",
) -> dict:
    """Build a single Product Hunt post node as returned by GraphQL API."""
    return {
        "id": post_id,
        "name": name,
        "tagline": tagline,
        "website": website,
        "url": url,
        "createdAt": created_at,
    }


def _make_graphql_response(edges: list[dict]) -> dict:
    """Build a minimal Product Hunt GraphQL posts response."""
    nodes = [e.get("node", e) for e in edges]
    return {
        "data": {
            "posts": {
                "edges": [{"node": n, "cursor": f"c{i}"} for i, n in enumerate(nodes)],
                "nodes": nodes,
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }


class TestProductHuntAdapterSourceName:
    """Tests for source_name property."""

    def test_producthunt_adapter_source_name(self) -> None:
        """Returns 'producthunt'."""
        adapter = ProductHuntAdapter()
        assert adapter.source_name == "producthunt"


class TestProductHuntAdapterNoToken:
    """Tests when PRODUCTHUNT_API_TOKEN is unset or empty."""

    @patch.dict("os.environ", {"PRODUCTHUNT_API_TOKEN": ""}, clear=False)
    def test_producthunt_adapter_returns_empty_when_no_token(self) -> None:
        """No token (empty string) -> fetch_events returns []."""
        adapter = ProductHuntAdapter()
        events = adapter.fetch_events(since=datetime(2026, 2, 1, tzinfo=UTC))
        assert events == []


class TestProductHuntAdapterMockedHttp:
    """Tests with mocked HTTP responses."""

    @patch.dict("os.environ", {"PRODUCTHUNT_API_TOKEN": "test-token"}, clear=False)
    @patch("app.ingestion.adapters.producthunt_adapter.httpx")
    def test_producthunt_adapter_returns_raw_events_when_mocked(
        self, mock_httpx: MagicMock
    ) -> None:
        """Mock HTTP returns RawEvents with valid shape and event_type_candidate."""
        node = _make_post_node()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_graphql_response([node])
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        adapter = ProductHuntAdapter()
        events = adapter.fetch_events(since=datetime(2026, 2, 1, tzinfo=UTC))

        assert len(events) >= 1
        raw = events[0]
        assert raw.company_name == "Acme Product"
        assert raw.domain == "acme.com"
        assert raw.website_url == "https://acme.com"
        assert raw.event_type_candidate == "launch_major"
        assert raw.event_type_candidate in SIGNAL_EVENT_TYPES
        assert raw.source_event_id is not None
        assert raw.event_time.tzinfo is not None

    @patch.dict("os.environ", {"PRODUCTHUNT_API_TOKEN": "test-token"}, clear=False)
    @patch("app.ingestion.adapters.producthunt_adapter.httpx")
    def test_producthunt_adapter_maps_launch_to_launch_major(
        self, mock_httpx: MagicMock
    ) -> None:
        """Post nodes map to RawEvent with event_type_candidate='launch_major'."""
        node = _make_post_node()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_graphql_response([node])
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        adapter = ProductHuntAdapter()
        events = adapter.fetch_events(since=datetime(2026, 2, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].event_type_candidate == "launch_major"


class TestProductHuntAdapterRateLimit:
    """Tests for rate limit / non-200 handling."""

    @patch.dict("os.environ", {"PRODUCTHUNT_API_TOKEN": "test-token"}, clear=False)
    @patch("app.ingestion.adapters.producthunt_adapter.httpx")
    def test_producthunt_adapter_handles_rate_limit(self, mock_httpx: MagicMock) -> None:
        """429 or non-200 response -> returns [] without raising."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        adapter = ProductHuntAdapter()
        events = adapter.fetch_events(since=datetime(2026, 2, 1, tzinfo=UTC))

        assert isinstance(events, list)
        assert len(events) == 0


class TestProductHuntAdapterRespectsSince:
    """Tests that since parameter is passed to API."""

    @patch.dict("os.environ", {"PRODUCTHUNT_API_TOKEN": "test-token"}, clear=False)
    @patch("app.ingestion.adapters.producthunt_adapter.httpx")
    def test_producthunt_adapter_respects_since(self, mock_httpx: MagicMock) -> None:
        """since datetime is passed to GraphQL as postedAfter (ISO 8601)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_graphql_response([])
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        adapter = ProductHuntAdapter()
        since = datetime(2026, 2, 15, 10, 30, 0, tzinfo=UTC)
        adapter.fetch_events(since=since)

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args[1]
        body = call_kwargs["json"]
        variables = body.get("variables", {})
        posted_after = variables.get("postedAfter")
        assert posted_after is not None
        assert "2026-02-15" in posted_after
