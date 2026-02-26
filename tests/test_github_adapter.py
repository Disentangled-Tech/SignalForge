"""Tests for GitHub ingestion adapter (Issue #244, Phase 2)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.ingestion.adapters.github_adapter import GitHubAdapter


class TestGitHubAdapterSourceName:
    """source_name returns 'github'."""

    def test_github_adapter_source_name(self) -> None:
        """Adapter source_name is 'github'."""
        adapter = GitHubAdapter()
        assert adapter.source_name == "github"


class TestGitHubAdapterNoToken:
    """Returns [] when GITHUB_TOKEN/GITHUB_PAT unset."""

    def test_github_adapter_returns_empty_when_no_token(self) -> None:
        """Env unset → []."""
        adapter = GitHubAdapter()
        with patch(
            "app.ingestion.adapters.github_adapter._get_token",
            return_value=None,
        ):
            events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))
        assert events == []


class TestGitHubAdapterMocked:
    """Tests with mocked httpx."""

    def test_github_adapter_returns_raw_events_when_mocked(self) -> None:
        """Mock httpx, assert RawEvent shape, event_type_candidate='repo_activity'."""
        adapter = GitHubAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "12345678",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "acme/cool-repo"},
                "actor": {"login": "dev1"},
            }
        ]

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "acme/cool-repo",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) >= 1
        ev = events[0]
        assert ev.event_type_candidate == "repo_activity"
        assert ev.company_name
        assert ev.event_time
        assert ev.source_event_id
        assert len(ev.source_event_id) <= 255

    def test_github_adapter_deduplicates_by_source_event_id(self) -> None:
        """Same event in response twice → one RawEvent."""
        adapter = GitHubAdapter()
        event = {
            "id": "99999",
            "type": "PushEvent",
            "created_at": "2025-01-15T12:00:00Z",
            "repo": {"name": "org/repo"},
            "actor": {"login": "user"},
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [event, event]

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "org/repo",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1

    def test_github_adapter_respects_since(self) -> None:
        """Events older than since are filtered out."""
        adapter = GitHubAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "1",
                "type": "PushEvent",
                "created_at": "2024-06-01T00:00:00Z",
                "repo": {"name": "org/repo"},
                "actor": {"login": "user"},
            }
        ]

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "org/repo",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                # since is after the event's created_at
                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 0

    def test_github_adapter_includes_events_after_since(self) -> None:
        """Events after since are included."""
        adapter = GitHubAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "2",
                "type": "PushEvent",
                "created_at": "2025-02-01T12:00:00Z",
                "repo": {"name": "org/repo"},
                "actor": {"login": "user"},
            }
        ]

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "org/repo",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].event_time.year == 2025

    def test_github_adapter_returns_empty_when_no_repos_or_orgs(self) -> None:
        """INGEST_GITHUB_REPOS and INGEST_GITHUB_ORGS both unset → []."""
        adapter = GitHubAdapter()
        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
            },
            clear=False,
        ):
            with patch(
                "app.ingestion.adapters.github_adapter._get_repos_and_orgs",
                return_value=([], []),
            ):
                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))
        assert events == []

    def test_github_adapter_handles_api_error(self) -> None:
        """401/500 → [] without raising."""
        adapter = GitHubAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "org/repo",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client
                mock_client.get.return_value = mock_response

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert events == []

    def test_github_adapter_handles_404(self) -> None:
        """404 (repo not found) → skip repo, continue."""
        adapter = GitHubAdapter()
        mock_404 = MagicMock()
        mock_404.status_code = 404
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = [
            {
                "id": "3",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "org/valid-repo"},
                "actor": {"login": "user"},
            }
        ]

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "org/nonexistent,org/valid-repo",
            },
            clear=False,
        ):
            with patch("app.ingestion.adapters.github_adapter.httpx") as mock_httpx:
                mock_client = MagicMock()
                mock_httpx.Client.return_value.__enter__.return_value = mock_client
                mock_client.get.side_effect = [mock_404, mock_200]

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].raw_payload and events[0].raw_payload.get("repo") == "org/valid-repo"

    def test_github_adapter_populates_website_url_from_org_metadata(self) -> None:
        """When org API returns blog, RawEvent has website_url (Phase 3 company resolution)."""
        adapter = GitHubAdapter()
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "42",
                "type": "PushEvent",
                "created_at": "2025-01-20T10:00:00Z",
                "repo": {"name": "acme/cool-repo"},
                "actor": {"login": "dev"},
            }
        ]
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "acme",
            "blog": "https://acme.example.com",
            "html_url": "https://github.com/acme",
        }

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "acme/cool-repo",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                # Call order: orgs/acme (org metadata), repos/acme/cool-repo/events
                mock_client.get.side_effect = [mock_org, mock_events]
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url == "https://acme.example.com"
        assert events[0].company_name == "acme"

    def test_github_adapter_website_url_none_when_org_has_no_blog(self) -> None:
        """When org API returns empty blog, RawEvent has website_url=None."""
        adapter = GitHubAdapter()
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "99",
                "type": "PushEvent",
                "created_at": "2025-01-20T10:00:00Z",
                "repo": {"name": "noblog/repo"},
                "actor": {"login": "dev"},
            }
        ]
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "noblog",
            "blog": "",
            "html_url": "https://github.com/noblog",
        }

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "noblog/repo",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = [mock_org, mock_events]
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url is None

    def test_github_adapter_website_url_adds_https_when_blog_has_no_scheme(
        self,
    ) -> None:
        """Blog 'example.com' → website_url 'https://example.com'."""
        adapter = GitHubAdapter()
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "77",
                "type": "PushEvent",
                "created_at": "2025-01-20T10:00:00Z",
                "repo": {"name": "foo/bar"},
                "actor": {"login": "dev"},
            }
        ]
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "foo",
            "blog": "example.com",
            "html_url": "https://github.com/foo",
        }

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "foo/bar",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = [mock_org, mock_events]
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url == "https://example.com"
