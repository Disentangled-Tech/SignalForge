"""Tests for daily ingestion job orchestrator (Issue #90)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.ingestion.adapters.crunchbase_adapter import CrunchbaseAdapter
from app.ingestion.adapters.producthunt_adapter import ProductHuntAdapter
from app.ingestion.adapters.test_adapter import TestAdapter
from app.ingestion.base import SourceAdapter
from app.models import Company, JobRun, SignalEvent
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.schemas.signal import RawEvent


class FailingAdapter(SourceAdapter):
    """Adapter that raises on fetch_events for testing error handling."""

    @property
    def source_name(self) -> str:
        return "failing"

    def fetch_events(self, since: datetime) -> list[RawEvent]:
        raise RuntimeError("Adapter fetch failed")


_TEST_DOMAINS = ("testa.example.com", "testb.example.com", "testc.example.com")


@pytest.fixture(autouse=True)
def _cleanup_test_adapter_data(db: Session) -> None:
    """Remove test adapter data before each test (handles pre-existing data from prior runs)."""
    db.query(SignalEvent).filter(SignalEvent.source == "test").delete(
        synchronize_session="fetch"
    )
    db.query(Company).filter(Company.domain.in_(_TEST_DOMAINS)).delete(
        synchronize_session="fetch"
    )
    db.commit()


class TestRunIngestDaily:
    """Daily ingestion job orchestrator."""

    def test_run_ingest_daily_creates_job_run(self, db: Session) -> None:
        """JobRun created with job_type=ingest."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        result = run_ingest_daily(db)

        assert result["status"] == "completed"
        job = (
            db.query(JobRun)
            .filter(JobRun.job_type == "ingest")
            .order_by(JobRun.id.desc())
            .first()
        )
        assert job is not None
        assert job.status == "completed"
        assert job.finished_at is not None
        assert result["job_run_id"] == job.id

    def test_run_ingest_daily_sets_pack_id_and_workspace_id_for_audit(
        self, db: Session
    ) -> None:
        """When called without workspace_id/pack_id, JobRun gets defaults for audit."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        run_ingest_daily(db)

        job = (
            db.query(JobRun)
            .filter(JobRun.job_type == "ingest")
            .order_by(JobRun.id.desc())
            .first()
        )
        assert job is not None
        assert job.workspace_id == UUID(DEFAULT_WORKSPACE_ID)
        assert job.pack_id is not None

    def test_run_ingest_daily_uses_last_run_for_since(self, db: Session) -> None:
        """When previous ingest JobRun exists, since = its finished_at."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        # First run
        run_ingest_daily(db)
        last_job = (
            db.query(JobRun)
            .filter(JobRun.job_type == "ingest")
            .order_by(JobRun.id.desc())
            .first()
        )
        last_finished = last_job.finished_at

        # Second run - patch run_ingest to capture since
        captured_since = None

        def capture_since(inner_db, adapter, since, pack_id=None):
            nonlocal captured_since
            captured_since = since
            from app.ingestion.ingest import run_ingest
            return run_ingest(inner_db, adapter, since, pack_id=pack_id)

        with patch(
            "app.services.ingestion.ingest_daily.run_ingest",
            side_effect=capture_since,
        ):
            run_ingest_daily(db)

        assert captured_since is not None
        # since should be close to last job's finished_at (within 1 second)
        assert abs((captured_since - last_finished).total_seconds()) < 1

    def test_run_ingest_daily_fallback_since_when_no_previous(
        self, db: Session
    ) -> None:
        """When no previous ingest, since = now - 24h (within tolerance)."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        # Clear ingest JobRuns so we hit the fallback path (now - 24h)
        db.query(JobRun).filter(JobRun.job_type == "ingest").delete(
            synchronize_session="fetch"
        )
        db.commit()

        captured_since = None

        def capture_since(inner_db, adapter, since, pack_id=None):
            nonlocal captured_since
            captured_since = since
            from app.ingestion.ingest import run_ingest
            return run_ingest(inner_db, adapter, since, pack_id=pack_id)

        with patch(
            "app.services.ingestion.ingest_daily.run_ingest",
            side_effect=capture_since,
        ):
            run_ingest_daily(db)

        assert captured_since is not None
        # Ensure timezone-aware for comparison (DB may return naive)
        if captured_since.tzinfo is None:
            captured_since = captured_since.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        expected_min = now - timedelta(hours=25)
        expected_max = now - timedelta(hours=23)
        assert expected_min <= captured_since <= expected_max

    def test_run_ingest_daily_persists_events(self, db: Session) -> None:
        """Events inserted, companies created."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        result = run_ingest_daily(db)

        assert result["status"] == "completed"
        assert result["inserted"] == 3
        events = db.query(SignalEvent).filter(SignalEvent.source == "test").all()
        assert len(events) == 3
        assert all(e.company_id is not None for e in events)

    def test_run_ingest_daily_no_duplicates_on_second_run(
        self, db: Session
    ) -> None:
        """Second run skips duplicates (inserted=0, skipped_duplicate>0)."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        first = run_ingest_daily(db)
        assert first["inserted"] == 3

        second = run_ingest_daily(db)
        assert second["inserted"] == 0
        assert second["skipped_duplicate"] == 3

    def test_run_ingest_daily_adapter_error_logged_non_fatal(
        self, db: Session
    ) -> None:
        """If one adapter raises, others still run; errors in result."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        with patch(
            "app.services.ingestion.ingest_daily._get_adapters",
            return_value=[TestAdapter(), FailingAdapter()],
        ):
            result = run_ingest_daily(db)

        assert result["status"] == "completed"
        assert result["inserted"] == 3  # TestAdapter succeeded
        assert result["errors_count"] > 0
        assert "Adapter fetch failed" in (result.get("error") or "")

    def test_run_ingest_daily_sets_error_message_on_failure(
        self, db: Session
    ) -> None:
        """JobRun.error_message populated when errors occur."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        with patch(
            "app.services.ingestion.ingest_daily._get_adapters",
            return_value=[TestAdapter(), FailingAdapter()],
        ):
            run_ingest_daily(db)

        job = (
            db.query(JobRun)
            .filter(JobRun.job_type == "ingest")
            .order_by(JobRun.id.desc())
            .first()
        )
        assert job is not None
        assert job.error_message is not None
        assert "Adapter fetch failed" in job.error_message


class TestGetAdaptersUnit:
    """Unit tests for _get_adapters() env-based config (no DB)."""

    def test_test_adapter_takes_precedence_when_set(self) -> None:
        """INGEST_USE_TEST_ADAPTER=1 returns only TestAdapter, no Crunchbase/Product Hunt."""
        from app.services.ingestion.ingest_daily import _get_adapters

        with patch.dict(
            "os.environ",
            {
                "INGEST_USE_TEST_ADAPTER": "1",
                "INGEST_CRUNCHBASE_ENABLED": "1",
                "CRUNCHBASE_API_KEY": "some-key",
                "INGEST_PRODUCTHUNT_ENABLED": "1",
                "PRODUCTHUNT_API_TOKEN": "some-token",
            },
            clear=False,
        ):
            adapters = _get_adapters()

        assert len(adapters) == 1
        assert isinstance(adapters[0], TestAdapter)
        assert adapters[0].source_name == "test"

    def test_crunchbase_included_when_enabled_and_key_set(self) -> None:
        """INGEST_CRUNCHBASE_ENABLED=1 and CRUNCHBASE_API_KEY set → CrunchbaseAdapter."""
        from app.services.ingestion.ingest_daily import _get_adapters

        with patch.dict(
            "os.environ",
            {
                "INGEST_USE_TEST_ADAPTER": "",
                "INGEST_CRUNCHBASE_ENABLED": "1",
                "CRUNCHBASE_API_KEY": "my-api-key",
            },
            clear=False,
        ):
            adapters = _get_adapters()

        assert len(adapters) == 1
        assert isinstance(adapters[0], CrunchbaseAdapter)
        assert adapters[0].source_name == "crunchbase"

    def test_crunchbase_excluded_when_enabled_but_no_key(self) -> None:
        """INGEST_CRUNCHBASE_ENABLED=1 but CRUNCHBASE_API_KEY unset → no Crunchbase."""
        from app.services.ingestion.ingest_daily import _get_adapters

        with patch.dict(
            "os.environ",
            {
                "INGEST_USE_TEST_ADAPTER": "",
                "INGEST_CRUNCHBASE_ENABLED": "1",
                "CRUNCHBASE_API_KEY": "",
            },
            clear=False,
        ):
            adapters = _get_adapters()

        assert len(adapters) == 0

    def test_crunchbase_excluded_when_disabled(self) -> None:
        """INGEST_CRUNCHBASE_ENABLED=0 or unset → no Crunchbase."""
        from app.services.ingestion.ingest_daily import _get_adapters

        with patch.dict(
            "os.environ",
            {
                "INGEST_USE_TEST_ADAPTER": "",
                "INGEST_CRUNCHBASE_ENABLED": "0",
                "CRUNCHBASE_API_KEY": "key",
            },
            clear=False,
        ):
            adapters = _get_adapters()

        assert len(adapters) == 0

    def test_producthunt_included_when_enabled_and_token_set(self) -> None:
        """INGEST_PRODUCTHUNT_ENABLED=1 and PRODUCTHUNT_API_TOKEN set → ProductHuntAdapter."""
        from app.services.ingestion.ingest_daily import _get_adapters

        with patch.dict(
            "os.environ",
            {
                "INGEST_USE_TEST_ADAPTER": "",
                "INGEST_PRODUCTHUNT_ENABLED": "1",
                "PRODUCTHUNT_API_TOKEN": "my-token",
            },
            clear=False,
        ):
            adapters = _get_adapters()

        assert len(adapters) == 1
        assert isinstance(adapters[0], ProductHuntAdapter)
        assert adapters[0].source_name == "producthunt"

    def test_producthunt_excluded_when_enabled_but_no_token(self) -> None:
        """INGEST_PRODUCTHUNT_ENABLED=1 but PRODUCTHUNT_API_TOKEN unset → no Product Hunt."""
        from app.services.ingestion.ingest_daily import _get_adapters

        with patch.dict(
            "os.environ",
            {
                "INGEST_USE_TEST_ADAPTER": "",
                "INGEST_PRODUCTHUNT_ENABLED": "1",
                "PRODUCTHUNT_API_TOKEN": "",
            },
            clear=False,
        ):
            adapters = _get_adapters()

        assert len(adapters) == 0

    def test_producthunt_excluded_when_disabled(self) -> None:
        """INGEST_PRODUCTHUNT_ENABLED=0 or unset → no Product Hunt."""
        from app.services.ingestion.ingest_daily import _get_adapters

        with patch.dict(
            "os.environ",
            {
                "INGEST_USE_TEST_ADAPTER": "",
                "INGEST_PRODUCTHUNT_ENABLED": "0",
                "PRODUCTHUNT_API_TOKEN": "token",
            },
            clear=False,
        ):
            adapters = _get_adapters()

        assert len(adapters) == 0


class TestGetAdaptersCrunchbaseWiring:
    """Phase 2: run_ingest_daily uses Crunchbase when env configured (Issue #134)."""

    @patch("app.ingestion.adapters.crunchbase_adapter.httpx")
    def test_run_ingest_daily_uses_crunchbase_when_configured(
        self, mock_httpx, db: Session
    ) -> None:
        """With Crunchbase env set, run_ingest_daily invokes CrunchbaseAdapter."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        # Mock Crunchbase API to return empty page (no real HTTP)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"properties": {"entities": []}}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        captured_adapters: list = []

        def capture_adapters(inner_db, adapter, since, pack_id=None):
            captured_adapters.append(adapter)
            from app.ingestion.ingest import run_ingest
            return run_ingest(inner_db, adapter, since, pack_id=pack_id)

        with patch.dict(
            "os.environ",
            {
                "INGEST_USE_TEST_ADAPTER": "",
                "INGEST_CRUNCHBASE_ENABLED": "1",
                "CRUNCHBASE_API_KEY": "test-key",
            },
            clear=False,
        ):
            with patch(
                "app.services.ingestion.ingest_daily.run_ingest",
                side_effect=capture_adapters,
            ):
                run_ingest_daily(db)

        assert len(captured_adapters) == 1
        assert isinstance(captured_adapters[0], CrunchbaseAdapter)

    @patch("app.ingestion.adapters.producthunt_adapter.httpx")
    def test_run_ingest_daily_uses_producthunt_when_configured(
        self, mock_httpx, db: Session
    ) -> None:
        """With Product Hunt env set, run_ingest_daily invokes ProductHuntAdapter (Phase 3)."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        # Mock Product Hunt GraphQL to return empty page (no real HTTP)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "posts": {
                    "edges": [],
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        captured_adapters: list = []

        def capture_adapters(inner_db, adapter, since, pack_id=None):
            captured_adapters.append(adapter)
            from app.ingestion.ingest import run_ingest
            return run_ingest(inner_db, adapter, since, pack_id=pack_id)

        with patch.dict(
            "os.environ",
            {
                "INGEST_USE_TEST_ADAPTER": "",
                "INGEST_PRODUCTHUNT_ENABLED": "1",
                "PRODUCTHUNT_API_TOKEN": "test-token",
            },
            clear=False,
        ):
            with patch(
                "app.services.ingestion.ingest_daily.run_ingest",
                side_effect=capture_adapters,
            ):
                run_ingest_daily(db)

        assert len(captured_adapters) == 1
        assert isinstance(captured_adapters[0], ProductHuntAdapter)

    @patch("app.ingestion.adapters.crunchbase_adapter.httpx")
    @patch("app.ingestion.adapters.producthunt_adapter.httpx")
    def test_run_ingest_daily_uses_both_adapters_when_both_configured(
        self, mock_ph_httpx, mock_cb_httpx, db: Session
    ) -> None:
        """When both Crunchbase and Product Hunt enabled, both adapters returned."""
        from app.services.ingestion.ingest_daily import run_ingest_daily

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = [
            {"properties": {"entities": []}},
            {"data": {"posts": {"edges": [], "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}},
        ]
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_cb_httpx.Client.return_value = mock_client
        mock_ph_httpx.Client.return_value = mock_client

        captured_adapters: list = []

        def capture_adapters(inner_db, adapter, since, pack_id=None):
            captured_adapters.append(adapter)
            from app.ingestion.ingest import run_ingest
            return run_ingest(inner_db, adapter, since, pack_id=pack_id)

        with patch.dict(
            "os.environ",
            {
                "INGEST_USE_TEST_ADAPTER": "",
                "INGEST_CRUNCHBASE_ENABLED": "1",
                "CRUNCHBASE_API_KEY": "test-key",
                "INGEST_PRODUCTHUNT_ENABLED": "1",
                "PRODUCTHUNT_API_TOKEN": "test-token",
            },
            clear=False,
        ):
            with patch(
                "app.services.ingestion.ingest_daily.run_ingest",
                side_effect=capture_adapters,
            ):
                run_ingest_daily(db)

        assert len(captured_adapters) == 2
        types = {type(a).__name__ for a in captured_adapters}
        assert "CrunchbaseAdapter" in types
        assert "ProductHuntAdapter" in types
