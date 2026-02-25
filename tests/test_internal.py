"""Tests for internal job endpoints (/internal/run_scan, /internal/run_briefing)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.job_run import JobRun

# ── Fixtures ────────────────────────────────────────────────────────

VALID_TOKEN = "test-internal-token"  # matches conftest.py env setup


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    return db


# ── /internal/run_scan ──────────────────────────────────────────────


class TestRunScan:
    @patch("app.services.scan_orchestrator.run_scan_all", new_callable=AsyncMock)
    def test_valid_token_calls_run_scan_all(self, mock_scan, client: TestClient):
        """POST /internal/run_scan with valid token triggers scan."""
        job = JobRun(job_type="scan", status="completed")
        job.id = 42
        job.companies_processed = 5
        mock_scan.return_value = job

        response = client.post(
            "/internal/run_scan",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["job_run_id"] == 42
        assert data["companies_processed"] == 5
        mock_scan.assert_called_once()
        assert mock_scan.call_args[1]["workspace_id"] is None

    def test_missing_token_returns_422(self, client: TestClient):
        """POST /internal/run_scan without token header returns 422."""
        response = client.post("/internal/run_scan")
        assert response.status_code == 422

    def test_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_scan with wrong token returns 403."""
        response = client.post(
            "/internal/run_scan",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403

    @patch("app.services.scan_orchestrator.run_scan_all", new_callable=AsyncMock)
    def test_run_scan_with_workspace_id_passes_to_run_scan_all(
        self, mock_scan, client: TestClient
    ):
        """POST /internal/run_scan with workspace_id forwards it (Phase 3)."""
        job = JobRun(job_type="scan", status="completed")
        job.id = 43
        job.companies_processed = 2
        mock_scan.return_value = job

        response = client.post(
            "/internal/run_scan",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"workspace_id": "00000000-0000-0000-0000-000000000001"},
        )

        assert response.status_code == 200
        mock_scan.assert_called_once()
        call_kwargs = mock_scan.call_args[1]
        assert call_kwargs["workspace_id"] == "00000000-0000-0000-0000-000000000001"

    @patch("app.services.scan_orchestrator.run_scan_all", new_callable=AsyncMock)
    def test_scan_error_returns_failed(self, mock_scan, client: TestClient):
        """POST /internal/run_scan returns failed status on exception."""
        mock_scan.side_effect = RuntimeError("DB exploded")

        response = client.post(
            "/internal/run_scan",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "DB exploded" in data["error"]


# ── /internal/run_briefing ──────────────────────────────────────────


class TestRunBriefing:
    @patch("app.services.briefing.generate_briefing")
    def test_valid_token_calls_generate_briefing(
        self, mock_briefing, client: TestClient
    ):
        """POST /internal/run_briefing with valid token triggers briefing."""
        mock_briefing.return_value = [MagicMock(), MagicMock(), MagicMock()]

        response = client.post(
            "/internal/run_briefing",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["items_generated"] == 3
        mock_briefing.assert_called_once()
        assert mock_briefing.call_args[1]["workspace_id"] is None

    def test_missing_token_returns_422(self, client: TestClient):
        """POST /internal/run_briefing without token header returns 422."""
        response = client.post("/internal/run_briefing")
        assert response.status_code == 422

    def test_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_briefing with wrong token returns 403."""
        response = client.post(
            "/internal/run_briefing",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403

    @patch("app.services.briefing.generate_briefing")
    def test_run_briefing_with_workspace_id_passes_to_generate(
        self, mock_briefing, client: TestClient
    ):
        """POST /internal/run_briefing with workspace_id forwards it (Phase 3)."""
        mock_briefing.return_value = [MagicMock()]

        response = client.post(
            "/internal/run_briefing",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"workspace_id": "00000000-0000-0000-0000-000000000001"},
        )

        assert response.status_code == 200
        mock_briefing.assert_called_once()
        assert mock_briefing.call_args[1]["workspace_id"] == (
            "00000000-0000-0000-0000-000000000001"
        )

    @patch("app.services.briefing.generate_briefing")
    def test_briefing_error_returns_failed(
        self, mock_briefing, client: TestClient
    ):
        """POST /internal/run_briefing returns failed status on exception."""
        mock_briefing.side_effect = RuntimeError("LLM down")

        response = client.post(
            "/internal/run_briefing",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "LLM down" in data["error"]


# ── /internal/run_score ────────────────────────────────────────────


class TestRunScore:
    @patch("app.services.readiness.score_nightly.run_score_nightly")
    def test_valid_token_calls_run_score_nightly(
        self, mock_score, client: TestClient
    ):
        """POST /internal/run_score with valid token triggers score job."""
        mock_score.return_value = {
            "status": "completed",
            "job_run_id": 99,
            "companies_scored": 5,
            "companies_engagement": 4,
            "companies_esl_suppressed": 1,
            "companies_skipped": 2,
            "error": None,
        }

        response = client.post(
            "/internal/run_score",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["job_run_id"] == 99
        assert data["companies_scored"] == 5
        assert data["companies_engagement"] == 4
        assert data["companies_esl_suppressed"] == 1
        assert data["companies_skipped"] == 2
        mock_score.assert_called_once()

    def test_run_score_missing_token_returns_422(self, client: TestClient):
        """POST /internal/run_score without token header returns 422."""
        response = client.post("/internal/run_score")
        assert response.status_code == 422

    def test_run_score_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_score with wrong token returns 403."""
        response = client.post(
            "/internal/run_score",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403

    @patch("app.services.readiness.score_nightly.run_score_nightly")
    def test_run_score_error_returns_failed(self, mock_score, client: TestClient):
        """POST /internal/run_score returns failed status on exception."""
        mock_score.side_effect = RuntimeError("DB error")

        response = client.post(
            "/internal/run_score",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "DB error" in data["error"]

    @patch("app.pipeline.executor.run_stage")
    def test_run_score_with_workspace_and_pack_params(
        self, mock_run_stage, client: TestClient
    ):
        """POST /internal/run_score passes workspace_id and pack_id to executor."""
        mock_run_stage.return_value = {
            "status": "completed",
            "job_run_id": 99,
            "companies_scored": 0,
            "companies_engagement": 0,
            "companies_skipped": 0,
            "error": None,
        }
        workspace_id = "00000000-0000-0000-0000-000000000001"
        pack_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        response = client.post(
            "/internal/run_score",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"workspace_id": workspace_id, "pack_id": pack_id},
        )

        assert response.status_code == 200
        mock_run_stage.assert_called_once()
        call_kwargs = mock_run_stage.call_args[1]
        assert call_kwargs["workspace_id"] == workspace_id
        assert str(call_kwargs["pack_id"]) == pack_id

    def test_run_score_invalid_workspace_id_returns_422(
        self, client: TestClient
    ):
        """POST /internal/run_score with invalid workspace_id returns 422."""
        response = client.post(
            "/internal/run_score",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"workspace_id": "not-a-uuid"},
        )
        assert response.status_code == 422
        data = response.json()
        assert "workspace_id" in data.get("detail", "").lower()
        assert "uuid" in data.get("detail", "").lower()

    def test_run_score_invalid_pack_id_returns_422(self, client: TestClient):
        """POST /internal/run_score with invalid pack_id returns 422."""
        response = client.post(
            "/internal/run_score",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"pack_id": "not-a-uuid"},
        )
        assert response.status_code == 422
        data = response.json()
        assert "pack_id" in data.get("detail", "").lower()
        assert "uuid" in data.get("detail", "").lower()


# ── /internal/run_update_lead_feed ────────────────────────────────────


class TestRunUpdateLeadFeed:
    """Tests for POST /internal/run_update_lead_feed."""

    @patch("app.pipeline.executor.run_stage")
    def test_valid_token_calls_run_stage(
        self, mock_run_stage, client: TestClient
    ):
        """POST /internal/run_update_lead_feed with valid token triggers stage."""
        mock_run_stage.return_value = {
            "status": "completed",
            "job_run_id": 42,
            "rows_upserted": 5,
            "error": None,
        }

        response = client.post(
            "/internal/run_update_lead_feed",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["job_run_id"] == 42
        assert data["rows_upserted"] == 5
        mock_run_stage.assert_called_once()
        assert mock_run_stage.call_args[1]["job_type"] == "update_lead_feed"

    def test_run_update_lead_feed_missing_token_returns_422(
        self, client: TestClient
    ):
        """POST /internal/run_update_lead_feed without token returns 422."""
        response = client.post("/internal/run_update_lead_feed")
        assert response.status_code == 422

    def test_run_update_lead_feed_wrong_token_returns_403(
        self, client: TestClient
    ):
        """POST /internal/run_update_lead_feed with wrong token returns 403."""
        response = client.post(
            "/internal/run_update_lead_feed",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403

    def test_run_update_lead_feed_invalid_workspace_id_returns_422(
        self, client: TestClient
    ):
        """POST /internal/run_update_lead_feed with invalid workspace_id returns 422."""
        response = client.post(
            "/internal/run_update_lead_feed",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"workspace_id": "not-a-uuid"},
        )
        assert response.status_code == 422
        data = response.json()
        detail = str(data.get("detail", "")).lower()
        assert "workspace_id" in detail
        assert "uuid" in detail

    def test_run_update_lead_feed_invalid_pack_id_returns_422(
        self, client: TestClient
    ):
        """POST /internal/run_update_lead_feed with invalid pack_id returns 422."""
        response = client.post(
            "/internal/run_update_lead_feed",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"pack_id": "not-a-uuid"},
        )
        assert response.status_code == 422
        data = response.json()
        detail = str(data.get("detail", "")).lower()
        assert "pack_id" in detail
        assert "uuid" in detail


# ── /internal/run_backfill_lead_feed (Phase 3) ─────────────────────────


class TestRunBackfillLeadFeed:
    """Tests for POST /internal/run_backfill_lead_feed."""

    @patch("app.services.lead_feed.run_update.run_backfill_lead_feed")
    def test_valid_token_calls_run_backfill(
        self, mock_backfill, client: TestClient
    ):
        """POST /internal/run_backfill_lead_feed with valid token triggers backfill."""
        mock_backfill.return_value = {
            "status": "completed",
            "workspaces_processed": 2,
            "total_rows_upserted": 15,
            "errors": None,
        }

        response = client.post(
            "/internal/run_backfill_lead_feed",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["workspaces_processed"] == 2
        assert data["total_rows_upserted"] == 15
        mock_backfill.assert_called_once()

    def test_run_backfill_lead_feed_missing_token_returns_422(
        self, client: TestClient
    ):
        """POST /internal/run_backfill_lead_feed without token returns 422."""
        response = client.post("/internal/run_backfill_lead_feed")
        assert response.status_code == 422

    def test_run_backfill_lead_feed_wrong_token_returns_403(
        self, client: TestClient
    ):
        """POST /internal/run_backfill_lead_feed with wrong token returns 403."""
        response = client.post(
            "/internal/run_backfill_lead_feed",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403


# ── /internal/run_alert_scan ──────────────────────────────────────────


class TestRunAlertScan:
    @patch("app.services.readiness.alert_scan.run_alert_scan")
    def test_valid_token_calls_run_alert_scan(
        self, mock_alert_scan, client: TestClient
    ):
        """POST /internal/run_alert_scan with valid token triggers alert scan."""
        mock_alert_scan.return_value = {
            "status": "completed",
            "alerts_created": 2,
            "companies_scanned": 10,
        }

        response = client.post(
            "/internal/run_alert_scan",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["alerts_created"] == 2
        assert data["companies_scanned"] == 10
        mock_alert_scan.assert_called_once()

    def test_run_alert_scan_missing_token_returns_422(self, client: TestClient):
        """POST /internal/run_alert_scan without token header returns 422."""
        response = client.post("/internal/run_alert_scan")
        assert response.status_code == 422

    def test_run_alert_scan_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_alert_scan with wrong token returns 403."""
        response = client.post(
            "/internal/run_alert_scan",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403

    @patch("app.services.readiness.alert_scan.run_alert_scan")
    def test_run_alert_scan_error_returns_failed(
        self, mock_alert_scan, client: TestClient
    ):
        """POST /internal/run_alert_scan returns failed status on exception."""
        mock_alert_scan.side_effect = RuntimeError("Alert scan error")

        response = client.post(
            "/internal/run_alert_scan",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "Alert scan error" in data["error"]


# ── /internal/run_derive ────────────────────────────────────────────


class TestRunDerive:
    @patch("app.pipeline.executor.run_stage")
    def test_run_derive_valid_token_returns_same_shape(
        self, mock_run_stage, client: TestClient
    ):
        """POST /internal/run_derive with valid token returns expected keys."""
        mock_run_stage.return_value = {
            "status": "completed",
            "job_run_id": 88,
            "instances_upserted": 10,
            "events_processed": 10,
            "events_skipped": 0,
            "error": None,
        }

        response = client.post(
            "/internal/run_derive",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["job_run_id"] == 88
        assert data["instances_upserted"] == 10
        assert data["events_processed"] == 10
        mock_run_stage.assert_called_once()
        call_kwargs = mock_run_stage.call_args[1]
        assert call_kwargs["job_type"] == "derive"

    def test_run_derive_missing_token_returns_422(self, client: TestClient):
        """POST /internal/run_derive without token header returns 422."""
        response = client.post("/internal/run_derive")
        assert response.status_code == 422

    def test_run_derive_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_derive with wrong token returns 403."""
        response = client.post(
            "/internal/run_derive",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403

    def test_run_derive_returns_400_when_no_pack(self, client: TestClient):
        """POST /internal/run_derive returns 400 when executor raises (no pack, Phase 3)."""
        from fastapi import HTTPException

        def _raise_no_pack(*args, **kwargs):
            raise HTTPException(
                status_code=400,
                detail="Derive stage requires a pack; no pack available",
            )

        with patch(
            "app.pipeline.executor.run_stage",
            side_effect=_raise_no_pack,
        ):
            response = client.post(
                "/internal/run_derive",
                headers={"X-Internal-Token": VALID_TOKEN},
            )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Derive stage requires a pack" in str(data["detail"])


# ── /internal/run_ingest ────────────────────────────────────────────


class TestRunIngest:
    @patch("app.services.ingestion.ingest_daily.run_ingest_daily")
    def test_valid_token_calls_run_ingest_daily(
        self, mock_ingest, client: TestClient
    ):
        """POST /internal/run_ingest with valid token triggers ingest job."""
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
        assert data["status"] == "completed"
        assert data["job_run_id"] == 42
        assert data["inserted"] == 3
        assert data["skipped_duplicate"] == 0
        assert data["errors_count"] == 0
        mock_ingest.assert_called_once()

    def test_run_ingest_missing_token_returns_422(self, client: TestClient):
        """POST /internal/run_ingest without token header returns 422."""
        response = client.post("/internal/run_ingest")
        assert response.status_code == 422

    def test_run_ingest_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_ingest with wrong token returns 403."""
        response = client.post(
            "/internal/run_ingest",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403

    @patch("app.services.ingestion.ingest_daily.run_ingest_daily")
    def test_run_ingest_error_returns_failed(self, mock_ingest, client: TestClient):
        """POST /internal/run_ingest returns failed status on exception."""
        mock_ingest.side_effect = RuntimeError("Ingest failed")

        response = client.post(
            "/internal/run_ingest",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "Ingest failed" in data["error"]

