"""Tests for daily aggregation job (Issue #246, Phase 1)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.ingestion.adapters.test_adapter import TestAdapter
from app.ingestion.base import SourceAdapter
from app.models import Company, JobRun, SignalEvent
from app.schemas.signal import RawEvent
from app.services.aggregation.daily_aggregation import run_daily_aggregation


class _FailingAdapter(SourceAdapter):
    """Adapter that raises on fetch_events for testing error handling."""

    @property
    def source_name(self) -> str:
        return "failing"

    def fetch_events(self, since) -> list[RawEvent]:
        raise RuntimeError("Adapter fetch failed")

_TEST_DOMAINS = ("testa.example.com", "testb.example.com", "testc.example.com")
_AS_OF = date(2026, 2, 18)


@pytest.fixture(autouse=True)
def _cleanup_test_adapter_data(db: Session) -> None:
    """Remove test adapter data before each test."""
    db.query(SignalEvent).filter(SignalEvent.source == "test").delete(
        synchronize_session="fetch"
    )
    db.query(Company).filter(Company.domain.in_(_TEST_DOMAINS)).delete(
        synchronize_session="fetch"
    )
    db.commit()


class TestRunDailyAggregationCallsStagesInOrder:
    """Orchestrator invokes ingest → derive → score in order."""

    def test_run_daily_aggregation_calls_stages_in_order(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """run_daily_aggregation invokes ingest → derive → score."""
        call_order: list[str] = []

        def capture_ingest(inner_db, workspace_id=None, pack_id=None):
            call_order.append("ingest")
            return {
                "status": "completed",
                "job_run_id": 1,
                "inserted": 0,
                "skipped_duplicate": 0,
                "skipped_invalid": 0,
                "errors_count": 0,
                "error": None,
            }

        def capture_derive(inner_db, workspace_id=None, pack_id=None):
            call_order.append("derive")
            return {
                "status": "completed",
                "job_run_id": 2,
                "instances_upserted": 0,
                "events_processed": 0,
                "events_skipped": 0,
                "error": None,
            }

        def capture_score(inner_db, workspace_id=None, pack_id=None):
            call_order.append("score")
            return {
                "status": "completed",
                "job_run_id": 3,
                "companies_scored": 0,
                "companies_engagement": 0,
                "companies_esl_suppressed": 0,
                "companies_skipped": 0,
                "error": None,
            }

        with (
            patch(
                "app.services.ingestion.ingest_daily.run_ingest_daily",
                side_effect=capture_ingest,
            ),
            patch(
                "app.pipeline.deriver_engine.run_deriver",
                side_effect=capture_derive,
            ),
            patch(
                "app.services.readiness.score_nightly.run_score_nightly",
                side_effect=capture_score,
            ),
            patch("app.services.aggregation.daily_aggregation.date") as mock_date,
        ):
            mock_date.today.return_value = _AS_OF
            result = run_daily_aggregation(db, pack_id=fractional_cto_pack_id)

        assert result["status"] == "completed"
        assert call_order == ["ingest", "derive", "score"]


class TestRunDailyAggregationProviderFailureNonFatal:
    """One adapter failure does not stop the job."""

    def test_run_daily_aggregation_provider_failure_non_fatal(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """When ingest has adapter errors, derive and score still run."""
        with (
            patch(
                "app.services.ingestion.ingest_daily._get_adapters",
                return_value=[TestAdapter(), _FailingAdapter()],
            ),
            patch("app.services.aggregation.daily_aggregation.date") as mock_date,
        ):
            mock_date.today.return_value = _AS_OF
            result = run_daily_aggregation(db, pack_id=fractional_cto_pack_id)

        assert result["status"] == "completed"
        assert result["ingest_result"]["status"] == "completed"
        assert result["ingest_result"]["inserted"] == 3
        assert result["ingest_result"]["errors_count"] > 0
        assert result["derive_result"]["status"] == "completed"
        assert result["score_result"]["status"] == "completed"


class TestRunDailyAggregationNoDuplicatesOnRerun:
    """Re-run does not duplicate SignalEvents."""

    def test_run_daily_aggregation_no_duplicates_on_rerun(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Second run does not duplicate SignalEvents (idempotency)."""
        with patch("app.services.aggregation.daily_aggregation.date") as mock_date:
            mock_date.today.return_value = _AS_OF

            first = run_daily_aggregation(db, pack_id=fractional_cto_pack_id)
            assert first["status"] == "completed"
            events_after_first = (
                db.query(SignalEvent).filter(SignalEvent.source == "test").count()
            )
            assert events_after_first == 3

            second = run_daily_aggregation(db, pack_id=fractional_cto_pack_id)
            assert second["status"] == "completed"
            events_after_second = (
                db.query(SignalEvent).filter(SignalEvent.source == "test").count()
            )
            assert events_after_second == 3
            assert second["ingest_result"]["inserted"] == 0
            assert second["ingest_result"]["skipped_duplicate"] == 3


class TestRunDailyAggregationReturnsRankedCompanies:
    """Result includes ranked_companies; console output logged."""

    def test_run_daily_aggregation_returns_ranked_companies(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Result includes ranked_companies with expected shape."""
        with patch("app.services.aggregation.daily_aggregation.date") as mock_date:
            mock_date.today.return_value = _AS_OF
            result = run_daily_aggregation(db, pack_id=fractional_cto_pack_id)

        assert result["status"] == "completed"
        assert "ranked_companies" in result
        assert isinstance(result["ranked_companies"], list)
        assert result["ranked_count"] == len(result["ranked_companies"])
        for item in result["ranked_companies"]:
            assert "company_name" in item
            assert "composite" in item
            assert "band" in item


class TestRunDailyAggregationUsesWorkspacePack:
    """Passes workspace_id and pack_id to stages."""

    def test_run_daily_aggregation_uses_workspace_pack(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """run_daily_aggregation passes workspace_id and pack_id to each stage."""
        captured: dict[str, dict] = {}

        orig_ingest = __import__(
            "app.services.ingestion.ingest_daily", fromlist=["run_ingest_daily"]
        ).run_ingest_daily

        def wrap_ingest(inner_db, workspace_id=None, pack_id=None):
            captured["ingest"] = {"workspace_id": workspace_id, "pack_id": pack_id}
            return orig_ingest(inner_db, workspace_id=workspace_id, pack_id=pack_id)

        orig_derive = __import__(
            "app.pipeline.deriver_engine", fromlist=["run_deriver"]
        ).run_deriver

        def wrap_derive(inner_db, workspace_id=None, pack_id=None):
            captured["derive"] = {"workspace_id": workspace_id, "pack_id": pack_id}
            return orig_derive(inner_db, workspace_id=workspace_id, pack_id=pack_id)

        orig_score = __import__(
            "app.services.readiness.score_nightly", fromlist=["run_score_nightly"]
        ).run_score_nightly

        def wrap_score(inner_db, workspace_id=None, pack_id=None):
            captured["score"] = {"workspace_id": workspace_id, "pack_id": pack_id}
            return orig_score(inner_db, workspace_id=workspace_id, pack_id=pack_id)

        ws_id = "00000000-0000-0000-0000-000000000001"
        with (
            patch(
                "app.services.ingestion.ingest_daily.run_ingest_daily",
                side_effect=wrap_ingest,
            ),
            patch(
                "app.pipeline.deriver_engine.run_deriver",
                side_effect=wrap_derive,
            ),
            patch(
                "app.services.readiness.score_nightly.run_score_nightly",
                side_effect=wrap_score,
            ),
            patch("app.services.aggregation.daily_aggregation.date") as mock_date,
        ):
            mock_date.today.return_value = _AS_OF
            run_daily_aggregation(
                db, workspace_id=ws_id, pack_id=fractional_cto_pack_id
            )

        assert captured["ingest"]["workspace_id"] == ws_id
        assert captured["ingest"]["pack_id"] == fractional_cto_pack_id
        assert captured["derive"]["workspace_id"] == ws_id
        assert captured["derive"]["pack_id"] == fractional_cto_pack_id
        assert captured["score"]["workspace_id"] == ws_id
        assert captured["score"]["pack_id"] == fractional_cto_pack_id


class TestRunDailyAggregationCreatesJobRun:
    """Creates JobRun with job_type=daily_aggregation."""

    def test_run_daily_aggregation_creates_job_run(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """JobRun created with job_type=daily_aggregation for audit."""
        with patch("app.services.aggregation.daily_aggregation.date") as mock_date:
            mock_date.today.return_value = _AS_OF
            result = run_daily_aggregation(db, pack_id=fractional_cto_pack_id)

        job = (
            db.query(JobRun)
            .filter(JobRun.job_type == "daily_aggregation")
            .order_by(JobRun.id.desc())
            .first()
        )
        assert job is not None
        assert job.status == "completed"
        assert result["job_run_id"] == job.id
