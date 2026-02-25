"""Tests for Crunchbase ingestion adapter (Phase 1, Issue #134)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.ingestion.adapters.crunchbase_adapter import CrunchbaseAdapter
from app.ingestion.event_types import SIGNAL_EVENT_TYPES


def _make_funding_round_response(entities: list[dict]) -> dict:
    """Build a minimal Crunchbase API v4 funding_rounds search response."""
    return {"properties": {"entities": entities}}


def _make_funding_entity(
    *,
    uuid: str = "fr-uuid-1",
    announced_on: str = "2026-02-20",
    org_name: str = "Acme Corp",
    org_domain: str = "acme.com",
    org_url: str = "https://acme.com",
    money_usd: int = 5_000_000,
    investment_type: str = "series_a",
) -> dict:
    """Build a single funding round entity as returned by Crunchbase API."""
    return {
        "identifier": {"uuid": uuid, "value": f"funding-{uuid}"},
        "announced_on": {"value": announced_on},
        "funded_organization_identifier": {"uuid": "org-uuid", "value": "acme-corp"},
        "money_raised": {"value_usd": money_usd},
        "investment_type": investment_type,
        "funded_organization_card": {
            "name": org_name,
            "domain": org_domain,
            "homepage_url": org_url,
        },
    }


class TestCrunchbaseAdapterSourceName:
    """Tests for source_name property."""

    def test_crunchbase_adapter_source_name(self) -> None:
        """Returns 'crunchbase'."""
        adapter = CrunchbaseAdapter()
        assert adapter.source_name == "crunchbase"


class TestCrunchbaseAdapterNoApiKey:
    """Tests when CRUNCHBASE_API_KEY is unset or empty."""

    @patch.dict("os.environ", {"CRUNCHBASE_API_KEY": ""}, clear=False)
    def test_crunchbase_adapter_returns_empty_when_no_api_key(self) -> None:
        """No API key (empty string) -> fetch_events returns []."""
        adapter = CrunchbaseAdapter()
        events = adapter.fetch_events(since=datetime(2026, 2, 1, tzinfo=UTC))
        assert events == []


class TestCrunchbaseAdapterMockedHttp:
    """Tests with mocked HTTP responses."""

    @patch.dict("os.environ", {"CRUNCHBASE_API_KEY": "test-key"}, clear=False)
    @patch("app.ingestion.adapters.crunchbase_adapter.httpx")
    def test_crunchbase_adapter_returns_raw_events_when_mocked(
        self, mock_httpx: MagicMock
    ) -> None:
        """Mock HTTP returns RawEvents with valid shape and event_type_candidate."""
        entity = _make_funding_entity()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_funding_round_response([entity])
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        adapter = CrunchbaseAdapter()
        events = adapter.fetch_events(since=datetime(2026, 2, 1, tzinfo=UTC))

        assert len(events) >= 1
        raw = events[0]
        assert raw.company_name == "Acme Corp"
        assert raw.domain == "acme.com"
        assert raw.website_url == "https://acme.com"
        assert raw.event_type_candidate == "funding_raised"
        assert raw.event_type_candidate in SIGNAL_EVENT_TYPES
        assert raw.source_event_id is not None
        assert raw.event_time.tzinfo is not None


class TestCrunchbaseAdapterRateLimit:
    """Tests for rate limit handling."""

    @patch.dict("os.environ", {"CRUNCHBASE_API_KEY": "test-key"}, clear=False)
    @patch("app.ingestion.adapters.crunchbase_adapter.httpx")
    def test_crunchbase_adapter_handles_rate_limit(self, mock_httpx: MagicMock) -> None:
        """429 response -> returns [] or partial results without raising."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        adapter = CrunchbaseAdapter()
        events = adapter.fetch_events(since=datetime(2026, 2, 1, tzinfo=UTC))

        # Graceful: return empty rather than raise
        assert isinstance(events, list)
        assert len(events) == 0


class TestCrunchbaseAdapterRespectsSince:
    """Tests that since parameter is passed to API."""

    @patch.dict("os.environ", {"CRUNCHBASE_API_KEY": "test-key"}, clear=False)
    @patch("app.ingestion.adapters.crunchbase_adapter.httpx")
    def test_crunchbase_adapter_respects_since(self, mock_httpx: MagicMock) -> None:
        """since datetime is passed to API query (announced_on gte filter)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_funding_round_response([])
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        adapter = CrunchbaseAdapter()
        since = datetime(2026, 2, 15, 10, 30, 0, tzinfo=UTC)
        adapter.fetch_events(since=since)

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args[1]
        body = call_kwargs["json"]
        query = body.get("query", [])
        announced_predicates = [
            q for q in query
            if isinstance(q, dict) and q.get("field_id") == "announced_on"
        ]
        assert len(announced_predicates) >= 1
        pred = announced_predicates[0]
        assert pred.get("operator_id") == "gte"
        # since date should appear in values (YYYY-MM-DD)
        values = pred.get("values", [])
        assert len(values) >= 1
        assert "2026-02-15" in str(values)
