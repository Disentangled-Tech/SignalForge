"""Tests for GitHub ingestion adapter (Issue #244, Phase 2)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.ingestion.adapters.github_adapter import (
    GitHubAdapter,
    clear_owner_metadata_cache,
)


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


@patch("app.ingestion.adapters.github_adapter.time.sleep")
class TestGitHubAdapterMocked:
    """Tests with mocked httpx. time.sleep is mocked to avoid 0.5s delay per owner metadata fetch."""

    def test_github_adapter_returns_raw_events_when_mocked(self, mock_sleep: MagicMock) -> None:
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

    def test_github_adapter_deduplicates_by_source_event_id(self, mock_sleep: MagicMock) -> None:
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

    def test_github_adapter_respects_since(self, mock_sleep: MagicMock) -> None:
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

    def test_github_adapter_includes_events_after_since(self, mock_sleep: MagicMock) -> None:
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

    def test_github_adapter_returns_empty_when_no_repos_or_orgs(
        self, mock_sleep: MagicMock
    ) -> None:
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

    def test_github_adapter_handles_api_error(self, mock_sleep: MagicMock) -> None:
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

    def test_github_adapter_handles_404(self, mock_sleep: MagicMock) -> None:
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
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()

                def _mock_get(*args, **kwargs):
                    url_str = str(args[0]) if args else str(kwargs.get("url", ""))
                    if "/orgs/" in url_str or "/users/" in url_str:
                        return mock_404
                    if "/repos/org/nonexistent/" in url_str:
                        return mock_404
                    return mock_200

                mock_client.get.side_effect = _mock_get
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].raw_payload and events[0].raw_payload.get("repo") == "org/valid-repo"

    def test_github_adapter_populates_website_url_from_org_metadata(
        self, mock_sleep: MagicMock
    ) -> None:
        """Org with blog → RawEvent.website_url set (Phase 3 company resolution)."""
        adapter = GitHubAdapter()
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "acme",
            "blog": "https://acme.example.com",
            "html_url": "https://github.com/acme",
        }
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "ev1",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "acme/repo"},
                "actor": {"login": "dev"},
            }
        ]

        def _mock_get(*args, **kwargs):
            url_str = str(args[0]) if args else str(kwargs.get("url", ""))
            if "/orgs/" in url_str or "/users/" in url_str:
                return mock_org
            return mock_events

        with patch.dict(
            "os.environ",
            {"GITHUB_TOKEN": "test-token", "INGEST_GITHUB_REPOS": "acme/repo"},
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = _mock_get
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url == "https://acme.example.com"

    def test_github_adapter_website_url_none_when_org_has_no_blog(
        self, mock_sleep: MagicMock
    ) -> None:
        """Org with empty blog → website_url=None."""
        adapter = GitHubAdapter()
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "noblog",
            "blog": "",
            "html_url": "https://github.com/noblog",
        }
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "ev2",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "noblog/repo"},
                "actor": {"login": "dev"},
            }
        ]

        def _mock_get(*args, **kwargs):
            url_str = str(args[0]) if args else str(kwargs.get("url", ""))
            if "/orgs/" in url_str or "/users/" in url_str:
                return mock_org
            return mock_events

        with patch.dict(
            "os.environ",
            {"GITHUB_TOKEN": "test-token", "INGEST_GITHUB_REPOS": "noblog/repo"},
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = _mock_get
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url is None

    def test_github_adapter_website_url_adds_https_when_blog_has_no_scheme(
        self, mock_sleep: MagicMock
    ) -> None:
        """Blog 'example.com' → website_url 'https://example.com'."""
        adapter = GitHubAdapter()
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "bare",
            "blog": "example.com",
            "html_url": "https://github.com/bare",
        }
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "ev3",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "bare/repo"},
                "actor": {"login": "dev"},
            }
        ]

        def _mock_get(*args, **kwargs):
            url_str = str(args[0]) if args else str(kwargs.get("url", ""))
            if "/orgs/" in url_str or "/users/" in url_str:
                return mock_org
            return mock_events

        with patch.dict(
            "os.environ",
            {"GITHUB_TOKEN": "test-token", "INGEST_GITHUB_REPOS": "bare/repo"},
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = _mock_get
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url == "https://example.com"

    def test_github_adapter_website_url_none_when_blog_is_github(
        self, mock_sleep: MagicMock
    ) -> None:
        """Blog pointing to github.com → website_url=None (org profile, not company site)."""
        adapter = GitHubAdapter()
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "ghorg",
            "blog": "https://github.com/ghorg",
            "html_url": "https://github.com/ghorg",
        }
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "ev4",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "ghorg/repo"},
                "actor": {"login": "dev"},
            }
        ]

        def _mock_get(*args, **kwargs):
            url_str = str(args[0]) if args else str(kwargs.get("url", ""))
            if "/orgs/" in url_str or "/users/" in url_str:
                return mock_org
            return mock_events

        with patch.dict(
            "os.environ",
            {"GITHUB_TOKEN": "test-token", "INGEST_GITHUB_REPOS": "ghorg/repo"},
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = _mock_get
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url is None

    def test_github_adapter_org_events_use_owner_metadata(self, mock_sleep: MagicMock) -> None:
        """Org events (INGEST_GITHUB_ORGS) fetch owner metadata for website_url."""
        adapter = GitHubAdapter()
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "myorg",
            "blog": "https://myorg.io",
            "html_url": "https://github.com/myorg",
        }
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "org-ev1",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "myorg/some-repo"},
                "actor": {"login": "dev"},
            }
        ]

        def _mock_get(*args, **kwargs):
            url_str = str(args[0]) if args else str(kwargs.get("url", ""))
            # /orgs/X or /users/X (no /events) -> org/user metadata
            if "/orgs/" in url_str and "/events" not in url_str:
                return mock_org
            if "/users/" in url_str and "/events" not in url_str:
                return mock_org
            return mock_events

        with patch.dict(
            "os.environ",
            {"GITHUB_TOKEN": "test-token", "INGEST_GITHUB_ORGS": "myorg"},
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = _mock_get
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url == "https://myorg.io"
        assert events[0].company_name == "myorg"

    def test_github_adapter_push_event_commit_url_from_payload(self, mock_sleep: MagicMock) -> None:
        """PushEvent with payload.head uses commit URL."""
        adapter = GitHubAdapter()
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "acme",
            "blog": "",
            "html_url": "https://github.com/acme",
        }
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "push1",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "acme/repo"},
                "actor": {"login": "dev"},
                "payload": {"head": "abc123def", "before": "000"},
            }
        ]

        def _mock_get(*args, **kwargs):
            url_str = str(args[0]) if args else str(kwargs.get("url", ""))
            if "/orgs/" in url_str or "/users/" in url_str:
                return mock_org
            return mock_events

        with patch.dict(
            "os.environ",
            {"GITHUB_TOKEN": "test-token", "INGEST_GITHUB_REPOS": "acme/repo"},
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = _mock_get
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert "commit/abc123def" in (events[0].url or "")


@patch("app.ingestion.adapters.github_adapter.time.sleep")
class TestGitHubAdapterMetadataCache:
    """Owner metadata cache reduces API calls across runs (follow-up #4)."""

    def test_github_adapter_metadata_cache_hit_skips_api_call(
        self, mock_sleep: MagicMock, tmp_path: Path
    ) -> None:
        """When cache has valid entry for owner, no /orgs/ or /users/ GET."""
        clear_owner_metadata_cache()
        cache_file = tmp_path / "github_owner_metadata.json"
        cache_file.write_text(
            json.dumps(
                {
                    "acme": {
                        "blog": "https://acme.example.com",
                        "html_url": "https://github.com/acme",
                        "cached_at": datetime.now(UTC).isoformat(),
                    }
                }
            )
        )

        adapter = GitHubAdapter()
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "ev1",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "acme/repo"},
                "actor": {"login": "dev"},
            }
        ]

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "acme/repo",
                "INGEST_GITHUB_CACHE_DIR": str(tmp_path),
                "INGEST_GITHUB_METADATA_CACHE_TTL_SECS": "86400",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.return_value = mock_events
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url == "https://acme.example.com"
        # Only events endpoint called, not orgs/users metadata
        call_urls = [
            str(c[0][0]) if c[0] else str(c[1].get("url", ""))
            for c in mock_client.get.call_args_list
        ]
        assert not any("/orgs/" in u or "/users/" in u for u in call_urls)

    def test_github_adapter_metadata_cache_miss_fetches_and_stores(
        self, mock_sleep: MagicMock, tmp_path: Path
    ) -> None:
        """When cache empty, fetch metadata and store in cache file."""
        clear_owner_metadata_cache()

        adapter = GitHubAdapter()
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "neworg",
            "blog": "https://neworg.io",
            "html_url": "https://github.com/neworg",
        }
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "ev1",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "neworg/repo"},
                "actor": {"login": "dev"},
            }
        ]

        def _mock_get(*args, **kwargs):
            url_str = str(args[0]) if args else str(kwargs.get("url", ""))
            if "/orgs/" in url_str or "/users/" in url_str:
                return mock_org
            return mock_events

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "neworg/repo",
                "INGEST_GITHUB_CACHE_DIR": str(tmp_path),
                "INGEST_GITHUB_METADATA_CACHE_TTL_SECS": "86400",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = _mock_get
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url == "https://neworg.io"
        cache_file = tmp_path / "github_owner_metadata.json"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert "neworg" in data
        assert data["neworg"]["blog"] == "https://neworg.io"

    def test_github_adapter_metadata_cache_ttl_expired_refetches(
        self, mock_sleep: MagicMock, tmp_path: Path
    ) -> None:
        """When cache entry expired (TTL=1, old cached_at), refetch from API."""
        clear_owner_metadata_cache()
        from datetime import timedelta

        old_time = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
        cache_file = tmp_path / "github_owner_metadata.json"
        cache_file.write_text(
            json.dumps(
                {
                    "stale": {
                        "blog": "https://old.example.com",
                        "html_url": "https://github.com/stale",
                        "cached_at": old_time,
                    }
                }
            )
        )

        adapter = GitHubAdapter()
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "stale",
            "blog": "https://fresh.example.com",
            "html_url": "https://github.com/stale",
        }
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "ev1",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "stale/repo"},
                "actor": {"login": "dev"},
            }
        ]

        def _mock_get(*args, **kwargs):
            url_str = str(args[0]) if args else str(kwargs.get("url", ""))
            if "/orgs/" in url_str or "/users/" in url_str:
                return mock_org
            return mock_events

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "stale/repo",
                "INGEST_GITHUB_CACHE_DIR": str(tmp_path),
                "INGEST_GITHUB_METADATA_CACHE_TTL_SECS": "1",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = _mock_get
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url == "https://fresh.example.com"
        data = json.loads(cache_file.read_text())
        assert data["stale"]["blog"] == "https://fresh.example.com"

    def test_github_adapter_metadata_cache_disabled_when_ttl_zero(
        self, mock_sleep: MagicMock, tmp_path: Path
    ) -> None:
        """When INGEST_GITHUB_METADATA_CACHE_TTL_SECS=0, cache disabled, always fetch."""
        clear_owner_metadata_cache()
        cache_file = tmp_path / "github_owner_metadata.json"
        cache_file.write_text(
            json.dumps(
                {
                    "acme": {
                        "blog": "https://cached.example.com",
                        "html_url": "https://github.com/acme",
                        "cached_at": datetime.now(UTC).isoformat(),
                    }
                }
            )
        )

        adapter = GitHubAdapter()
        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {
            "login": "acme",
            "blog": "https://api-fetched.example.com",
            "html_url": "https://github.com/acme",
        }
        mock_events = MagicMock()
        mock_events.status_code = 200
        mock_events.json.return_value = [
            {
                "id": "ev1",
                "type": "PushEvent",
                "created_at": "2025-01-15T12:00:00Z",
                "repo": {"name": "acme/repo"},
                "actor": {"login": "dev"},
            }
        ]

        def _mock_get(*args, **kwargs):
            url_str = str(args[0]) if args else str(kwargs.get("url", ""))
            if "/orgs/" in url_str or "/users/" in url_str:
                return mock_org
            return mock_events

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "INGEST_GITHUB_REPOS": "acme/repo",
                "INGEST_GITHUB_CACHE_DIR": str(tmp_path),
                "INGEST_GITHUB_METADATA_CACHE_TTL_SECS": "0",
            },
            clear=False,
        ):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = _mock_get
                mock_client_cls.return_value.__enter__.return_value = mock_client

                events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].website_url == "https://api-fetched.example.com"
