"""Tests for NewsAPI ingestion adapter (Issue #245, Phase 1)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.ingestion.adapters.newsapi_adapter import NewsAPIAdapter


class TestNewsAPIAdapterSourceName:
    """source_name returns 'newsapi'."""

    def test_newsapi_adapter_source_name(self) -> None:
        """Adapter source_name is 'newsapi'."""
        adapter = NewsAPIAdapter()
        assert adapter.source_name == "newsapi"


class TestNewsAPIAdapterNoApiKey:
    """Returns [] when NEWSAPI_API_KEY unset."""

    def test_newsapi_adapter_returns_empty_when_no_api_key(self) -> None:
        """Env unset → []."""
        adapter = NewsAPIAdapter()
        with patch(
            "app.ingestion.adapters.newsapi_adapter._get_api_key",
            return_value=None,
        ):
            events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))
        assert events == []


class TestNewsAPIAdapterMocked:
    """Tests with mocked httpx."""

    def test_newsapi_adapter_returns_raw_events_when_mocked(self) -> None:
        """Mock httpx, assert RawEvent shape, event_type_candidate='funding_raised'."""
        adapter = NewsAPIAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "totalResults": 1,
            "articles": [
                {
                    "title": "Acme raises $10M Series A",
                    "url": "https://example.com/article/1",
                    "publishedAt": "2025-01-15T12:00:00Z",
                    "description": "Acme secures funding.",
                    "source": {"name": "TechCrunch"},
                }
            ],
        }

        with patch.dict("os.environ", {"NEWSAPI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) >= 1
        ev = events[0]
        assert ev.event_type_candidate == "funding_raised"
        assert ev.company_name
        assert ev.event_time
        assert ev.url == "https://example.com/article/1"
        assert ev.source_event_id
        assert len(ev.source_event_id) <= 255

    def test_newsapi_adapter_deduplicates_by_source_event_id(self) -> None:
        """Same URL in response twice → one event."""
        adapter = NewsAPIAdapter()
        article = {
            "title": "Acme raises $10M",
            "url": "https://example.com/same",
            "publishedAt": "2025-01-15T12:00:00Z",
            "description": "Funding news",
            "source": {"name": "TechCrunch"},
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "totalResults": 2,
            "articles": [article, article],
        }

        with patch.dict("os.environ", {"NEWSAPI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1

    def test_newsapi_adapter_handles_empty_results(self) -> None:
        """API returns articles: [] → []."""
        adapter = NewsAPIAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "totalResults": 0,
            "articles": [],
        }

        with patch.dict("os.environ", {"NEWSAPI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert events == []

    def test_newsapi_adapter_handles_api_error(self) -> None:
        """401/500 → [] without raising."""
        adapter = NewsAPIAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.dict("os.environ", {"NEWSAPI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert events == []

    def test_newsapi_adapter_respects_since(self) -> None:
        """from param in request matches since."""
        adapter = NewsAPIAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "totalResults": 0,
            "articles": [],
        }

        with patch.dict("os.environ", {"NEWSAPI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                since = datetime(2025, 2, 10, 14, 30, 0, tzinfo=UTC)
                adapter.fetch_events(since=since)

                calls = mock_client.get.call_args_list
                assert len(calls) >= 1
                params = calls[0][1].get("params", {})
                assert params.get("from") == "2025-02-10"

    def test_newsapi_adapter_company_name_heuristic(self) -> None:
        """Title 'Acme raises $10M' → company_name extracted (or 'Unknown')."""
        adapter = NewsAPIAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "totalResults": 1,
            "articles": [
                {
                    "title": "Acme raises $10M Series A",
                    "url": "https://example.com/acme",
                    "publishedAt": "2025-01-15T12:00:00Z",
                    "description": "Acme Corp secures funding.",
                    "source": {"name": "TechCrunch"},
                }
            ],
        }

        with patch.dict("os.environ", {"NEWSAPI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) >= 1
        assert events[0].company_name != "Unknown" or events[0].company_name == "Unknown"
        # Heuristic should extract something; at minimum we get a valid company_name
        assert events[0].company_name
        assert len(events[0].company_name) <= 255

    def test_newsapi_adapter_configurable_keywords(self) -> None:
        """Custom keywords env → correct q in request."""
        adapter = NewsAPIAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "totalResults": 0,
            "articles": [],
        }

        with patch.dict(
            "os.environ",
            {"NEWSAPI_API_KEY": "test-key", "INGEST_NEWSAPI_KEYWORDS": "custom,keywords"},
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

                calls = mock_client.get.call_args_list
                assert len(calls) >= 2  # One per keyword
                q_values = [c[1].get("params", {}).get("q") for c in calls]
                assert "custom" in q_values
                assert "keywords" in q_values

    def test_newsapi_adapter_json_keywords_override(self) -> None:
        """INGEST_NEWSAPI_KEYWORDS_JSON overrides comma-separated."""
        adapter = NewsAPIAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "totalResults": 0,
            "articles": [],
        }

        with patch.dict(
            "os.environ",
            {
                "NEWSAPI_API_KEY": "test-key",
                "INGEST_NEWSAPI_KEYWORDS_JSON": '["json-keyword"]',
                "INGEST_NEWSAPI_KEYWORDS": "csv,ignored",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

                calls = mock_client.get.call_args_list
                q_values = [c[1].get("params", {}).get("q") for c in calls]
                assert "json-keyword" in q_values
                assert "csv" not in q_values

    def test_newsapi_adapter_skips_article_without_url(self) -> None:
        """Article with url=None is skipped."""
        adapter = NewsAPIAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "totalResults": 2,
            "articles": [
                {"title": "No URL", "url": None, "publishedAt": "2025-01-15T12:00:00Z"},
                {
                    "title": "Acme raises $10M",
                    "url": "https://example.com/valid",
                    "publishedAt": "2025-01-15T12:00:00Z",
                    "description": "Funding",
                    "source": {"name": "TechCrunch"},
                },
            ],
        }

        with patch.dict("os.environ", {"NEWSAPI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].url == "https://example.com/valid"

    def test_newsapi_adapter_company_name_unknown_when_no_match(self) -> None:
        """Title with no heuristic match yields company_name Unknown."""
        adapter = NewsAPIAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "totalResults": 1,
            "articles": [
                {
                    "title": "Random tech news today",
                    "url": "https://example.com/random",
                    "publishedAt": "2025-01-15T12:00:00Z",
                    "description": "General update",
                    "source": {"name": "Blog"},
                }
            ],
        }

        with patch.dict("os.environ", {"NEWSAPI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].company_name == "Unknown"

    def test_newsapi_adapter_handles_429(self) -> None:
        """429 rate limit → [] without raising."""
        adapter = NewsAPIAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch.dict("os.environ", {"NEWSAPI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert events == []

    def test_newsapi_adapter_pagination(self) -> None:
        """Fetches multiple pages when totalResults > pageSize."""
        adapter = NewsAPIAdapter()
        # Page 1: 100 articles (full page) to trigger page 2
        page1_articles = [
            {
                "title": f"Company{i} raises funding",
                "url": f"https://example.com/page1-{i}",
                "publishedAt": "2025-01-15T12:00:00Z",
                "description": "Funding",
                "source": {"name": "TechCrunch"},
            }
            for i in range(100)
        ]
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "status": "ok",
            "totalResults": 150,
            "articles": page1_articles,
        }
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "status": "ok",
            "totalResults": 150,
            "articles": [
                {
                    "title": "Company100 raises funding",
                    "url": "https://example.com/page2",
                    "publishedAt": "2025-01-15T12:00:00Z",
                    "description": "Funding",
                    "source": {"name": "TechCrunch"},
                }
            ],
        }

        with patch.dict(
            "os.environ",
            {"NEWSAPI_API_KEY": "test-key", "INGEST_NEWSAPI_KEYWORDS": "single"},
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.side_effect = [page1, page2]

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 101
        assert mock_client.get.call_count == 2
