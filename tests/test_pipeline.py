"""Tests for pipeline executor, stages, rate limits (Phase 1, Issue #192)."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import JobRun, Workspace
from app.pipeline.executor import run_stage
from app.pipeline.rate_limits import check_workspace_rate_limit
from app.pipeline.stages import DEFAULT_WORKSPACE_ID

VALID_TOKEN = "test-internal-token"

OTHER_WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"


class TestRunStage:
    """Tests for run_stage executor."""

    @patch("app.services.ingestion.ingest_daily.run_ingest_daily")
    def test_run_stage_ingest_calls_run_ingest_daily(self, mock_ingest, db: Session) -> None:
        """run_stage('ingest') calls run_ingest_daily with workspace_id and pack_id."""
        mock_ingest.return_value = {
            "status": "completed",
            "job_run_id": 1,
            "inserted": 0,
            "skipped_duplicate": 0,
            "skipped_invalid": 0,
            "errors_count": 0,
            "error": None,
        }
        result = run_stage(db, job_type="ingest")
        assert result["status"] == "completed"
        assert result["job_run_id"] == 1
        mock_ingest.assert_called_once()
        call_kwargs = mock_ingest.call_args[1]
        assert call_kwargs["workspace_id"] == DEFAULT_WORKSPACE_ID
        assert call_kwargs["pack_id"] is not None

    @patch("app.services.readiness.score_nightly.run_score_nightly")
    def test_run_stage_score_calls_run_score_nightly(self, mock_score, db: Session) -> None:
        """run_stage('score') calls run_score_nightly with workspace_id and pack_id."""
        mock_score.return_value = {
            "status": "completed",
            "job_run_id": 2,
            "companies_scored": 3,
            "companies_engagement": 2,
            "companies_skipped": 0,
            "error": None,
        }
        result = run_stage(db, job_type="score")
        assert result["status"] == "completed"
        assert result["job_run_id"] == 2
        mock_score.assert_called_once()
        call_kwargs = mock_score.call_args[1]
        assert call_kwargs["workspace_id"] == DEFAULT_WORKSPACE_ID
        assert call_kwargs["pack_id"] is not None

    @patch("app.services.readiness.score_nightly.run_score_nightly")
    def test_run_stage_score_uses_workspace_active_pack_when_pack_id_omitted(
        self, mock_score, db: Session, fractional_cto_pack_id
    ) -> None:
        """When workspace has active_pack_id and pack_id omitted, score stage uses that pack."""
        mock_score.return_value = {
            "status": "completed",
            "job_run_id": 2,
            "companies_scored": 0,
            "companies_engagement": 0,
            "companies_skipped": 0,
            "error": None,
        }
        other_ws = Workspace(
            id=UUID(OTHER_WORKSPACE_ID),
            name="Other",
            active_pack_id=fractional_cto_pack_id,
        )
        db.add(other_ws)
        db.commit()

        result = run_stage(
            db,
            job_type="score",
            workspace_id=OTHER_WORKSPACE_ID,
            pack_id=None,
        )
        assert result["status"] == "completed"
        mock_score.assert_called_once()
        call_kwargs = mock_score.call_args[1]
        assert call_kwargs["workspace_id"] == OTHER_WORKSPACE_ID
        assert call_kwargs["pack_id"] == str(fractional_cto_pack_id)

    def test_run_stage_unknown_job_type_raises(self, db: Session) -> None:
        """run_stage with unknown job_type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown job_type"):
            run_stage(db, job_type="unknown_stage")

    @patch("app.pipeline.deriver_engine.run_deriver")
    def test_run_stage_derive_calls_run_deriver(self, mock_deriver, db: Session) -> None:
        """run_stage('derive') without pack_id calls run_deriver with pack_id=None (Issue #287 M2)."""
        mock_deriver.return_value = {
            "status": "completed",
            "job_run_id": 3,
            "instances_upserted": 5,
            "events_processed": 5,
            "events_skipped": 0,
        }
        result = run_stage(db, job_type="derive", pack_id=None)
        assert result["status"] == "completed"
        assert result["job_run_id"] == 3
        assert result["instances_upserted"] == 5
        mock_deriver.assert_called_once()
        call_kwargs = mock_deriver.call_args[1]
        assert call_kwargs["workspace_id"] == DEFAULT_WORKSPACE_ID
        assert call_kwargs["pack_id"] is None

    @patch("app.services.lead_feed.run_update.run_update_lead_feed")
    def test_run_stage_update_lead_feed_calls_run_update(
        self, mock_run_update, db: Session
    ) -> None:
        """run_stage('update_lead_feed') calls run_update_lead_feed."""
        mock_run_update.return_value = {
            "status": "completed",
            "job_run_id": 4,
            "rows_upserted": 10,
            "error": None,
        }
        result = run_stage(db, job_type="update_lead_feed")
        assert result["status"] == "completed"
        assert result["job_run_id"] == 4
        assert result["rows_upserted"] == 10
        mock_run_update.assert_called_once()
        call_kwargs = mock_run_update.call_args[1]
        assert call_kwargs["workspace_id"] == DEFAULT_WORKSPACE_ID
        assert call_kwargs["pack_id"] is not None
    def test_run_stage_update_lead_feed_calls_stage(self, db: Session) -> None:
        """run_stage('update_lead_feed') runs update_lead_feed stage (Phase 3)."""
        result = run_stage(db, job_type="update_lead_feed")
        assert result["status"] in ("completed", "skipped")
        assert "job_run_id" in result
        assert "rows_upserted" in result


class TestIdempotency:
    """Tests for idempotency_key behavior."""

    def test_idempotency_key_returns_cached_when_completed_exists(self, db: Session) -> None:
        """When idempotency_key matches completed run, return cached result."""
        job = JobRun(
            job_type="ingest",
            status="completed",
            idempotency_key="test-key-123",
            companies_processed=5,
            workspace_id=UUID(DEFAULT_WORKSPACE_ID),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        with patch("app.services.ingestion.ingest_daily.run_ingest_daily") as mock_ingest:
            result = run_stage(
                db,
                job_type="ingest",
                idempotency_key="test-key-123",
            )
            mock_ingest.assert_not_called()
            assert result["status"] == "completed"
            assert result["job_run_id"] == job.id
            assert result["inserted"] == 5

    def test_idempotency_isolated_by_workspace(self, db: Session, fractional_cto_pack_id) -> None:
        """Same idempotency_key in different workspaces returns each workspace's cached result."""
        other_ws = Workspace(
            id=UUID(OTHER_WORKSPACE_ID),
            name="Other",
            active_pack_id=fractional_cto_pack_id,
        )
        db.add(other_ws)
        db.flush()

        job_ws_a = JobRun(
            job_type="ingest",
            status="completed",
            idempotency_key="shared-key",
            companies_processed=10,
            workspace_id=UUID(DEFAULT_WORKSPACE_ID),
        )
        job_ws_b = JobRun(
            job_type="ingest",
            status="completed",
            idempotency_key="shared-key",
            companies_processed=20,
            workspace_id=UUID(OTHER_WORKSPACE_ID),
        )
        db.add(job_ws_a)
        db.add(job_ws_b)
        db.commit()
        db.refresh(job_ws_a)
        db.refresh(job_ws_b)

        with patch("app.services.ingestion.ingest_daily.run_ingest_daily") as mock_ingest:
            result_a = run_stage(
                db,
                job_type="ingest",
                workspace_id=DEFAULT_WORKSPACE_ID,
                idempotency_key="shared-key",
            )
            result_b = run_stage(
                db,
                job_type="ingest",
                workspace_id=OTHER_WORKSPACE_ID,
                idempotency_key="shared-key",
            )
            result_default = run_stage(
                db,
                job_type="ingest",
                idempotency_key="shared-key",
            )

        mock_ingest.assert_not_called()
        assert result_a["job_run_id"] == job_ws_a.id
        assert result_a["inserted"] == 10
        assert result_b["job_run_id"] == job_ws_b.id
        assert result_b["inserted"] == 20
        assert result_default["job_run_id"] == job_ws_a.id
        assert result_default["inserted"] == 10

    def test_idempotency_update_lead_feed_returns_cached_when_completed_exists(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """When idempotency_key matches completed update_lead_feed run, return cached result."""
        job = JobRun(
            job_type="update_lead_feed",
            status="completed",
            idempotency_key="lead-feed-key-001",
            companies_processed=3,
            workspace_id=UUID(DEFAULT_WORKSPACE_ID),
            pack_id=fractional_cto_pack_id,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        with patch(
            "app.services.lead_feed.run_update.run_update_lead_feed"
        ) as mock_update:
            result = run_stage(
                db,
                job_type="update_lead_feed",
                idempotency_key="lead-feed-key-001",
            )
            mock_update.assert_not_called()
            assert result["status"] == "completed"
            assert result["job_run_id"] == job.id
            assert result["rows_upserted"] == 3


class TestRateLimit:
    """Tests for workspace rate limits."""

    def test_check_workspace_rate_limit_disabled_returns_true(self, db: Session) -> None:
        """When limit is 0 (disabled), check always returns True."""
        with patch("app.pipeline.rate_limits.get_settings") as mock_settings:
            mock_settings.return_value.workspace_job_rate_limit_per_hour = 0
            assert check_workspace_rate_limit(db, DEFAULT_WORKSPACE_ID, "ingest")

    def test_check_workspace_rate_limit_under_limit_returns_true(self, db: Session) -> None:
        """When under limit, check returns True."""
        with patch("app.pipeline.rate_limits.get_settings") as mock_settings:
            mock_settings.return_value.workspace_job_rate_limit_per_hour = 10
            with patch.object(db, "scalar", return_value=5):
                assert check_workspace_rate_limit(db, DEFAULT_WORKSPACE_ID, "ingest")

    def test_rate_limit_returns_429_when_exceeded(self, client: TestClient) -> None:
        """POST /internal/run_ingest returns 429 when rate limit exceeded."""
        with patch(
            "app.pipeline.executor.check_workspace_rate_limit",
            return_value=False,
        ):
            response = client.post(
                "/internal/run_ingest",
                headers={"X-Internal-Token": VALID_TOKEN},
            )
            assert response.status_code == 429
            assert "rate limit" in response.json().get("detail", "").lower()

    @pytest.mark.integration
    def test_rate_limit_query_uses_index(self, db: Session) -> None:
        """ix_job_runs_workspace_job_started exists for rate limit query performance."""
        from sqlalchemy import inspect

        from app.db import engine

        inspector = inspect(engine)
        indexes = inspector.get_indexes("job_runs")
        index_names = [idx["name"] for idx in indexes]
        assert "ix_job_runs_workspace_job_started" in index_names


class TestInternalEndpointsViaExecutor:
    """Verify internal endpoints use executor and return same response shape."""

    @patch("app.services.ingestion.ingest_daily.run_ingest_daily")
    def test_run_ingest_returns_same_shape(self, mock_ingest, client: TestClient) -> None:
        """POST /internal/run_ingest returns expected keys."""
        mock_ingest.return_value = {
            "status": "completed",
            "job_run_id": 42,
            "inserted": 3,
            "skipped_duplicate": 0,
            "skipped_invalid": 0,
            "errors_count": 0,
            "error": None,
        }
        response = client.post(
            "/internal/run_ingest",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "job_run_id" in data
        assert "inserted" in data
        assert "skipped_duplicate" in data
        assert "errors_count" in data

    @patch("app.services.readiness.score_nightly.run_score_nightly")
    def test_run_score_returns_same_shape(self, mock_score, client: TestClient) -> None:
        """POST /internal/run_score returns expected keys."""
        mock_score.return_value = {
            "status": "completed",
            "job_run_id": 99,
            "companies_scored": 5,
            "companies_engagement": 4,
            "companies_skipped": 2,
            "error": None,
        }
        response = client.post(
            "/internal/run_score",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "job_run_id" in data
        assert "companies_scored" in data
        assert "companies_engagement" in data
        assert "companies_skipped" in data

    def test_run_update_lead_feed_returns_same_shape(
        self, client: TestClient
    ) -> None:
        """POST /internal/run_update_lead_feed returns expected keys (Phase 3)."""
        response = client.post(
            "/internal/run_update_lead_feed",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "job_run_id" in data
        assert "rows_upserted" in data
