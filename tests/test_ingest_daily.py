"""Tests for daily ingestion job orchestrator (Issue #90)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.ingestion.adapters.test_adapter import TestAdapter
from app.ingestion.base import SourceAdapter
from app.models import Company, JobRun, SignalEvent
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
            captured_since = captured_since.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
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
            result = run_ingest_daily(db)

        job = (
            db.query(JobRun)
            .filter(JobRun.job_type == "ingest")
            .order_by(JobRun.id.desc())
            .first()
        )
        assert job is not None
        assert job.error_message is not None
        assert "Adapter fetch failed" in job.error_message
