"""Tests for Delaware Socrata ingestion adapter (Issue #250, Phase 1)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.ingestion.adapters.delaware_socrata_adapter import DelawareSocrataAdapter


class TestDelawareSocrataAdapterSourceName:
    """source_name returns 'delaware_socrata'."""

    def test_delaware_socrata_adapter_source_name(self) -> None:
        """Adapter source_name is 'delaware_socrata'."""
        adapter = DelawareSocrataAdapter()
        assert adapter.source_name == "delaware_socrata"


class TestDelawareSocrataAdapterEmptyEnv:
    """Returns [] when INGEST_DELAWARE_SOCRATA_DATASET_ID unset."""

    def test_delaware_socrata_adapter_returns_empty_when_no_dataset_id(self) -> None:
        """Env unset → []."""
        adapter = DelawareSocrataAdapter()
        with patch(
            "app.ingestion.adapters.delaware_socrata_adapter._get_dataset_id",
            return_value=None,
        ):
            events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))
        assert events == []


@patch("app.ingestion.adapters.delaware_socrata_adapter.httpx")
class TestDelawareSocrataAdapterMocked:
    """Tests with mocked httpx."""

    def test_delaware_socrata_adapter_returns_raw_events_when_mocked(
        self, mock_httpx: MagicMock
    ) -> None:
        """Mock httpx, assert RawEvent shape, event_type_candidate='incorporation'."""
        adapter = DelawareSocrataAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "entity_name": "Acme Corp LLC",
                "file_date": "2025-01-15T00:00:00.000",
                "entity_type": "LLC",
            }
        ]

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        with patch.dict(
            "os.environ",
            {"INGEST_DELAWARE_SOCRATA_DATASET_ID": "test-ds-01"},
            clear=False,
        ):
            events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) >= 1
        ev = events[0]
        assert ev.event_type_candidate == "incorporation"
        assert ev.company_name == "Acme Corp LLC"
        assert ev.event_time
        assert ev.source_event_id
        assert len(ev.source_event_id) <= 255

    def test_delaware_socrata_adapter_deduplicates_by_source_event_id(
        self, mock_httpx: MagicMock
    ) -> None:
        """Same row in response twice → one RawEvent."""
        adapter = DelawareSocrataAdapter()
        row = {
            "entity_name": "Dup LLC",
            "file_date": "2025-01-15T00:00:00.000",
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [row, row]

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        with patch.dict(
            "os.environ",
            {"INGEST_DELAWARE_SOCRATA_DATASET_ID": "test-ds-02"},
            clear=False,
        ):
            events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1

    def test_delaware_socrata_adapter_respects_since(self, mock_httpx: MagicMock) -> None:
        """Events older than since are filtered out."""
        adapter = DelawareSocrataAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "entity_name": "Old Corp",
                "file_date": "2024-06-01T00:00:00.000",
            }
        ]

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        with patch.dict(
            "os.environ",
            {"INGEST_DELAWARE_SOCRATA_DATASET_ID": "test-ds-03"},
            clear=False,
        ):
            events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 0

    def test_delaware_socrata_adapter_includes_events_after_since(
        self, mock_httpx: MagicMock
    ) -> None:
        """Events after since are included."""
        adapter = DelawareSocrataAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "entity_name": "New Corp",
                "file_date": "2025-02-01T12:00:00.000",
            }
        ]

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        with patch.dict(
            "os.environ",
            {"INGEST_DELAWARE_SOCRATA_DATASET_ID": "test-ds-04"},
            clear=False,
        ):
            events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].event_time.year == 2025

    def test_delaware_socrata_adapter_handles_api_error(self, mock_httpx: MagicMock) -> None:
        """401/500 → [] without raising."""
        adapter = DelawareSocrataAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        with patch.dict(
            "os.environ",
            {"INGEST_DELAWARE_SOCRATA_DATASET_ID": "test-ds-05"},
            clear=False,
        ):
            events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert events == []

    def test_delaware_socrata_adapter_supports_restname_field(self, mock_httpx: MagicMock) -> None:
        """Datasets with restname (e.g. restaurant inspections) map company_name."""
        adapter = DelawareSocrataAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "restname": "13 Wingz",
                "insp_date": "2025-01-20T00:00:00.000",
            }
        ]

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        with patch.dict(
            "os.environ",
            {"INGEST_DELAWARE_SOCRATA_DATASET_ID": "384s-wygj"},
            clear=False,
        ):
            events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
        assert events[0].company_name == "13 Wingz"
        assert events[0].event_type_candidate == "incorporation"

    def test_delaware_socrata_adapter_rejects_invalid_date_column(
        self, mock_httpx: MagicMock
    ) -> None:
        """INGEST_DELAWARE_SOCRATA_DATE_COLUMN with invalid chars falls back to client-side filter."""
        adapter = DelawareSocrataAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "entity_name": "Valid Corp",
                "file_date": "2025-01-15T00:00:00.000",
            }
        ]

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        with patch.dict(
            "os.environ",
            {
                "INGEST_DELAWARE_SOCRATA_DATASET_ID": "test-ds",
                "INGEST_DELAWARE_SOCRATA_DATE_COLUMN": "file_date; DROP TABLE",
            },
            clear=False,
        ):
            events = adapter.fetch_events(since=datetime(2025, 1, 1, tzinfo=UTC))

        assert len(events) == 1
