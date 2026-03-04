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
    def test_run_scan_with_workspace_id_passes_to_run_scan_all(self, mock_scan, client: TestClient):
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
    def test_valid_token_calls_generate_briefing(self, mock_briefing, client: TestClient):
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
    def test_briefing_error_returns_failed(self, mock_briefing, client: TestClient):
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
    def test_valid_token_calls_run_score_nightly(self, mock_score, client: TestClient):
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
    def test_run_score_with_workspace_and_pack_params(self, mock_run_stage, client: TestClient):
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

    def test_run_score_invalid_workspace_id_returns_422(self, client: TestClient):
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
    def test_valid_token_calls_run_stage(self, mock_run_stage, client: TestClient):
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

    def test_run_update_lead_feed_missing_token_returns_422(self, client: TestClient):
        """POST /internal/run_update_lead_feed without token returns 422."""
        response = client.post("/internal/run_update_lead_feed")
        assert response.status_code == 422

    def test_run_update_lead_feed_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_update_lead_feed with wrong token returns 403."""
        response = client.post(
            "/internal/run_update_lead_feed",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403

    def test_run_update_lead_feed_invalid_workspace_id_returns_422(self, client: TestClient):
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

    def test_run_update_lead_feed_invalid_pack_id_returns_422(self, client: TestClient):
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
    def test_valid_token_calls_run_backfill(self, mock_backfill, client: TestClient):
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

    def test_run_backfill_lead_feed_missing_token_returns_422(self, client: TestClient):
        """POST /internal/run_backfill_lead_feed without token returns 422."""
        response = client.post("/internal/run_backfill_lead_feed")
        assert response.status_code == 422

    def test_run_backfill_lead_feed_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_backfill_lead_feed with wrong token returns 403."""
        response = client.post(
            "/internal/run_backfill_lead_feed",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403


# ── /internal/run_alert_scan ──────────────────────────────────────────


class TestRunAlertScan:
    @patch("app.services.readiness.alert_scan.run_alert_scan")
    def test_valid_token_calls_run_alert_scan(self, mock_alert_scan, client: TestClient):
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
        # When workspace_id omitted, endpoint resolves pack and passes pack_id (Issue #193)
        call_kwargs = mock_alert_scan.call_args[1]
        assert "pack_id" in call_kwargs
        assert call_kwargs["pack_id"] is not None

    @patch("app.services.pack_resolver.get_pack_for_workspace", return_value=None)
    @patch("app.services.pack_resolver.get_default_pack_id")
    @patch("app.services.readiness.alert_scan.run_alert_scan")
    def test_run_alert_scan_without_workspace_id_calls_with_resolved_pack_id(
        self,
        mock_alert_scan,
        mock_get_default_pack_id,
        _mock_get_pack_for_workspace,
        client: TestClient,
    ):
        """POST /internal/run_alert_scan without workspace_id calls run_alert_scan with resolved default pack_id."""
        import uuid

        resolved_pack_id = uuid.uuid4()
        mock_get_default_pack_id.return_value = resolved_pack_id
        mock_alert_scan.return_value = {
            "status": "completed",
            "alerts_created": 0,
            "companies_scanned": 0,
        }

        response = client.post(
            "/internal/run_alert_scan",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        mock_alert_scan.assert_called_once()
        call_kwargs = mock_alert_scan.call_args[1]
        assert call_kwargs["pack_id"] == resolved_pack_id

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
    def test_run_alert_scan_error_returns_failed(self, mock_alert_scan, client: TestClient):
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


# ── /internal/run_bias_audit ──────────────────────────────────────────


class TestRunBiasAudit:
    """POST /internal/run_bias_audit (Issue #112, workspace_id Issue #193)."""

    @patch("app.services.bias_audit.run_bias_audit")
    def test_run_bias_audit_without_workspace_id_calls_with_default_workspace_id(
        self, mock_audit, client: TestClient
    ):
        """POST /internal/run_bias_audit without workspace_id calls run_bias_audit with DEFAULT_WORKSPACE_ID."""
        from app.pipeline.stages import DEFAULT_WORKSPACE_ID

        mock_audit.return_value = {
            "status": "completed",
            "job_run_id": 1,
            "report_id": 42,
            "surfaced_count": 5,
            "flags": [],
        }

        response = client.post(
            "/internal/run_bias_audit",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["workspace_id"] == DEFAULT_WORKSPACE_ID

    @patch("app.services.bias_audit.run_bias_audit")
    def test_run_bias_audit_with_workspace_id_passes_through(self, mock_audit, client: TestClient):
        """POST /internal/run_bias_audit with workspace_id query param forwards it."""
        workspace_id = "00000000-0000-0000-0000-000000000002"
        mock_audit.return_value = {
            "status": "completed",
            "job_run_id": 1,
            "report_id": 43,
            "surfaced_count": 0,
            "flags": [],
        }

        response = client.post(
            "/internal/run_bias_audit",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"workspace_id": workspace_id},
        )

        assert response.status_code == 200
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["workspace_id"] == workspace_id


# ── /internal/run_monitor (M6, Issue #280) ───────────────────────────


class TestRunMonitor:
    """Tests for POST /internal/run_monitor (diff-based monitor full run + persistence)."""

    @patch("app.monitor.runner.run_monitor_full", new_callable=AsyncMock)
    def test_valid_token_calls_run_monitor_full(self, mock_run_monitor_full, client: TestClient):
        """POST /internal/run_monitor with valid token triggers run_monitor_full."""
        mock_run_monitor_full.return_value = {
            "status": "completed",
            "change_events_count": 1,
            "events_stored": 1,
            "events_skipped_duplicate": 0,
            "companies_processed": 2,
        }

        response = client.post(
            "/internal/run_monitor",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["change_events_count"] == 1
        assert data["events_stored"] == 1
        assert data["events_skipped_duplicate"] == 0
        assert data["companies_processed"] == 2
        mock_run_monitor_full.assert_called_once()

    def test_run_monitor_missing_token_returns_422(self, client: TestClient):
        """POST /internal/run_monitor without token header returns 422."""
        response = client.post("/internal/run_monitor")
        assert response.status_code == 422

    def test_run_monitor_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_monitor with wrong token returns 403."""
        response = client.post(
            "/internal/run_monitor",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403

    @patch("app.monitor.runner.run_monitor_full", new_callable=AsyncMock)
    def test_run_monitor_with_workspace_id_passes_to_run_monitor_full(
        self, mock_run_monitor_full, client: TestClient
    ):
        """POST /internal/run_monitor with workspace_id forwards it."""
        mock_run_monitor_full.return_value = {
            "status": "completed",
            "change_events_count": 0,
            "events_stored": 0,
            "events_skipped_duplicate": 0,
            "companies_processed": 0,
        }

        response = client.post(
            "/internal/run_monitor",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"workspace_id": "00000000-0000-0000-0000-000000000001"},
        )

        assert response.status_code == 200
        call_kwargs = mock_run_monitor_full.call_args[1]
        assert call_kwargs["workspace_id"] == "00000000-0000-0000-0000-000000000001"

    @patch("app.monitor.runner.run_monitor_full", new_callable=AsyncMock)
    def test_run_monitor_with_company_ids_passes_list(
        self, mock_run_monitor_full, client: TestClient
    ):
        """POST /internal/run_monitor with company_ids forwards parsed list."""
        mock_run_monitor_full.return_value = {
            "status": "completed",
            "change_events_count": 0,
            "events_stored": 0,
            "events_skipped_duplicate": 0,
            "companies_processed": 1,
        }

        response = client.post(
            "/internal/run_monitor",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"company_ids": "1,2,3"},
        )

        assert response.status_code == 200
        call_kwargs = mock_run_monitor_full.call_args[1]
        assert call_kwargs["company_ids"] == [1, 2, 3]

    def test_run_monitor_invalid_company_ids_returns_422(self, client: TestClient):
        """POST /internal/run_monitor with non-integer company_ids returns 422."""
        response = client.post(
            "/internal/run_monitor",
            headers={"X-Internal-Token": VALID_TOKEN},
            params={"company_ids": "1,not-a-number"},
        )
        assert response.status_code == 422

    @patch("app.monitor.runner.run_monitor_full", new_callable=AsyncMock)
    def test_run_monitor_error_returns_failed(self, mock_run_monitor_full, client: TestClient):
        """POST /internal/run_monitor returns failed status on exception."""
        mock_run_monitor_full.side_effect = RuntimeError("Monitor error")

        response = client.post(
            "/internal/run_monitor",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["change_events_count"] == 0
        assert data["events_stored"] == 0
        assert "Monitor error" in data["error"]


# ── /internal/run_derive ────────────────────────────────────────────


class TestRunDerive:
    @patch("app.pipeline.executor.run_stage")
    def test_run_derive_valid_token_returns_same_shape(self, mock_run_stage, client: TestClient):
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

    def test_run_derive_without_pack_returns_200(self, client: TestClient):
        """POST /internal/run_derive without pack_id returns 200 (Issue #287 M2).

        Derive runs without a pack; uses core pack. Response is 200 with status
        completed or skipped (never 400 for missing pack).
        """
        response = client.post(
            "/internal/run_derive",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("completed", "skipped")
        assert "job_run_id" in data
        assert "instances_upserted" in data
        assert "events_processed" in data

    def test_run_derive_without_pack_calls_stage_with_pack_id_none(
        self, client: TestClient
    ) -> None:
        """POST /internal/run_derive without pack_id passes pack_id=None to run_stage (M2)."""
        with patch("app.pipeline.executor.run_stage") as mock_run_stage:
            mock_run_stage.return_value = {
                "status": "completed",
                "job_run_id": 1,
                "instances_upserted": 0,
                "events_processed": 0,
                "events_skipped": 0,
                "error": None,
            }
            response = client.post(
                "/internal/run_derive",
                headers={"X-Internal-Token": VALID_TOKEN},
            )
        assert response.status_code == 200
        mock_run_stage.assert_called_once()
        call_kwargs = mock_run_stage.call_args[1]
        assert call_kwargs["job_type"] == "derive"
        assert call_kwargs["pack_id"] is None


# ── /internal/run_ingest ────────────────────────────────────────────


class TestRunIngest:
    @patch("app.services.ingestion.ingest_daily.run_ingest_daily")
    def test_valid_token_calls_run_ingest_daily(self, mock_ingest, client: TestClient):
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


# ── /internal/run_daily_aggregation ────────────────────────────────────────


class TestRunDailyAggregation:
    """Tests for POST /internal/run_daily_aggregation."""

    @patch("app.pipeline.executor.run_stage")
    def test_run_daily_aggregation_returns_expected_shape(self, mock_run_stage, client: TestClient):
        """POST /internal/run_daily_aggregation returns status, job_run_id, inserted, companies_scored, ranked_count, ranked_companies."""
        mock_run_stage.return_value = {
            "status": "completed",
            "job_run_id": 100,
            "ingest_result": {"inserted": 5},
            "score_result": {"companies_scored": 3},
            "ranked_count": 2,
            "ranked_companies": [
                {"company_name": "Acme Corp", "composite": 75, "band": "allow"},
                {"company_name": "Beta Inc", "composite": 60, "band": "nurture"},
            ],
            "error": None,
        }

        response = client.post(
            "/internal/run_daily_aggregation",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["job_run_id"] == 100
        assert data["inserted"] == 5
        assert data["companies_scored"] == 3
        assert data["ranked_count"] == 2
        assert "ranked_companies" in data
        assert len(data["ranked_companies"]) == 2
        assert data["ranked_companies"][0]["company_name"] == "Acme Corp"
        assert data["ranked_companies"][0]["composite"] == 75
        assert data["ranked_companies"][0]["band"] == "allow"
        mock_run_stage.assert_called_once()
        assert mock_run_stage.call_args[1]["job_type"] == "daily_aggregation"

    @patch("app.pipeline.executor.run_stage")
    def test_ranked_count_reflects_all_scored_companies_not_outreach_threshold(
        self, mock_run_stage, client: TestClient
    ):
        """ranked_count = all scored companies; outreach_score_threshold=0 is applied by orchestrator.

        The orchestrator passes outreach_score_threshold=0 to get_emerging_companies, so
        ranked_count includes every company with any readiness score, not just those above
        the configured outreach threshold (default 30). The API surfaces this count unchanged.
        """
        mock_run_stage.return_value = {
            "status": "completed",
            "job_run_id": 101,
            "ingest_result": {"inserted": 5},
            "score_result": {"companies_scored": 8},
            # 8 companies scored; all 8 appear in ranked_count because threshold=0
            "ranked_count": 8,
            "ranked_companies": [
                {"company_name": f"Co{i}", "composite": 50, "band": "allow"} for i in range(8)
            ],
            "error": None,
        }

        response = client.post(
            "/internal/run_daily_aggregation",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        # ranked_count surfaces the orchestrator's all-scored count, not a filtered subset
        assert data["ranked_count"] == 8
        assert data["companies_scored"] == 8

    def test_run_daily_aggregation_requires_token(self, client: TestClient):
        """POST /internal/run_daily_aggregation without token returns 422."""
        response = client.post("/internal/run_daily_aggregation")
        assert response.status_code == 422

    def test_run_daily_aggregation_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_daily_aggregation with wrong token returns 403."""
        response = client.post(
            "/internal/run_daily_aggregation",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403


# ── /internal/run_watchlist_seed (Issue #279 M3) ───────────────────────────────


class TestRunWatchlistSeed:
    """Tests for POST /internal/run_watchlist_seed."""

    @patch("app.pipeline.executor.run_stage")
    def test_valid_token_and_body_returns_seed_derive_score_results(
        self, mock_run_stage, client: TestClient
    ):
        """POST /internal/run_watchlist_seed with valid token and body returns combined results."""
        mock_run_stage.return_value = {
            "status": "completed",
            "job_run_id": 99,
            "seed_result": {
                "companies_created": 1,
                "companies_matched": 0,
                "events_stored": 2,
                "events_skipped_duplicate": 0,
                "errors": [],
            },
            "derive_result": {
                "status": "completed",
                "job_run_id": 10,
                "instances_upserted": 2,
                "events_processed": 2,
                "events_skipped": 0,
                "error": None,
            },
            "score_result": {
                "status": "completed",
                "job_run_id": 11,
                "companies_scored": 1,
                "companies_skipped": 0,
                "error": None,
            },
            "error": None,
        }
        bundle_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        response = client.post(
            "/internal/run_watchlist_seed",
            headers={"X-Internal-Token": VALID_TOKEN},
            json={"bundle_ids": [bundle_id]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["job_run_id"] == 99
        assert data["seed_result"]["events_stored"] == 2
        assert data["derive_result"]["instances_upserted"] == 2
        assert data["score_result"]["companies_scored"] == 1
        mock_run_stage.assert_called_once()
        call_kwargs = mock_run_stage.call_args[1]
        assert call_kwargs["job_type"] == "watchlist_seed"
        assert len(call_kwargs["bundle_ids"]) == 1
        assert str(call_kwargs["bundle_ids"][0]) == bundle_id

    def test_run_watchlist_seed_missing_token_returns_422(self, client: TestClient):
        """POST /internal/run_watchlist_seed without token returns 422."""
        response = client.post(
            "/internal/run_watchlist_seed",
            json={"bundle_ids": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]},
        )
        assert response.status_code == 422

    def test_run_watchlist_seed_wrong_token_returns_403(self, client: TestClient):
        """POST /internal/run_watchlist_seed with wrong token returns 403."""
        response = client.post(
            "/internal/run_watchlist_seed",
            headers={"X-Internal-Token": "wrong-token"},
            json={"bundle_ids": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]},
        )
        assert response.status_code == 403

    def test_run_watchlist_seed_missing_body_returns_422(self, client: TestClient):
        """POST /internal/run_watchlist_seed without body returns 422."""
        response = client.post(
            "/internal/run_watchlist_seed",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 422

    def test_run_watchlist_seed_empty_bundle_ids_returns_422(self, client: TestClient):
        """POST /internal/run_watchlist_seed with empty bundle_ids returns 422."""
        response = client.post(
            "/internal/run_watchlist_seed",
            headers={"X-Internal-Token": VALID_TOKEN},
            json={"bundle_ids": []},
        )
        assert response.status_code == 422

    @patch("app.pipeline.executor.run_stage")
    def test_run_watchlist_seed_with_workspace_and_pack_passes_through(
        self, mock_run_stage, client: TestClient
    ):
        """POST /internal/run_watchlist_seed passes workspace_id and pack_id to run_stage."""
        mock_run_stage.return_value = {
            "status": "completed",
            "job_run_id": 1,
            "seed_result": {},
            "derive_result": {"status": "completed"},
            "score_result": {"status": "completed"},
            "error": None,
        }
        bundle_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        workspace_id = "00000000-0000-0000-0000-000000000001"
        pack_id = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
        response = client.post(
            "/internal/run_watchlist_seed",
            headers={"X-Internal-Token": VALID_TOKEN},
            json={"bundle_ids": [bundle_id], "workspace_id": workspace_id},
            params={"pack_id": pack_id},
        )

        assert response.status_code == 200
        mock_run_stage.assert_called_once()
        call_kwargs = mock_run_stage.call_args[1]
        assert call_kwargs["job_type"] == "watchlist_seed"
        assert call_kwargs["workspace_id"] == workspace_id
        assert str(call_kwargs["pack_id"]) == pack_id

    @patch("app.pipeline.executor.run_stage")
    def test_run_watchlist_seed_error_returns_failed(self, mock_run_stage, client: TestClient):
        """POST /internal/run_watchlist_seed returns failed status when orchestration fails."""
        mock_run_stage.return_value = {
            "status": "failed",
            "job_run_id": None,
            "seed_result": {"events_stored": 0, "errors": ["Bundle not found"]},
            "derive_result": {},
            "score_result": {},
            "error": "No pack resolved for workspace",
        }
        response = client.post(
            "/internal/run_watchlist_seed",
            headers={"X-Internal-Token": VALID_TOKEN},
            json={"bundle_ids": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "No pack resolved" in data["error"]

    @patch("app.pipeline.executor.run_stage")
    def test_run_watchlist_seed_exception_returns_failed(self, mock_run_stage, client: TestClient):
        """POST /internal/run_watchlist_seed returns failed when run_stage raises."""
        mock_run_stage.side_effect = RuntimeError("DB connection lost")
        response = client.post(
            "/internal/run_watchlist_seed",
            headers={"X-Internal-Token": VALID_TOKEN},
            json={"bundle_ids": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "DB connection lost" in data["error"]

    @patch("app.api.internal.get_settings")
    def test_run_watchlist_seed_requires_workspace_id_when_multi_workspace_enabled(
        self, mock_get_settings, client: TestClient
    ):
        """POST /internal/run_watchlist_seed returns 422 when MULTI_WORKSPACE_ENABLED and workspace_id omitted."""
        settings = MagicMock()
        settings.multi_workspace_enabled = True
        settings.internal_job_token = VALID_TOKEN  # so _require_internal_token still passes
        mock_get_settings.return_value = settings
        response = client.post(
            "/internal/run_watchlist_seed",
            headers={"X-Internal-Token": VALID_TOKEN},
            json={"bundle_ids": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]},
        )
        assert response.status_code == 422
        data = response.json()
        assert "workspace_id" in data.get("detail", "").lower()
        assert "required" in data.get("detail", "").lower()

    @patch("app.pipeline.executor.run_stage")
    def test_run_watchlist_seed_passes_idempotency_key_to_run_stage(
        self, mock_run_stage, client: TestClient
    ):
        """POST /internal/run_watchlist_seed passes X-Idempotency-Key to run_stage."""
        mock_run_stage.return_value = {
            "status": "completed",
            "job_run_id": 1,
            "seed_result": {},
            "derive_result": {"status": "completed"},
            "score_result": {"status": "completed"},
            "error": None,
        }
        response = client.post(
            "/internal/run_watchlist_seed",
            headers={
                "X-Internal-Token": VALID_TOKEN,
                "X-Idempotency-Key": "ws1:2026-03-02T12:00:00",
            },
            json={"bundle_ids": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]},
        )
        assert response.status_code == 200
        mock_run_stage.assert_called_once()
        call_kwargs = mock_run_stage.call_args[1]
        assert call_kwargs["idempotency_key"] == "ws1:2026-03-02T12:00:00"

    def test_run_watchlist_seed_invalid_pack_id_returns_422(self, client: TestClient):
        """POST /internal/run_watchlist_seed with invalid pack_id query returns 422."""
        response = client.post(
            "/internal/run_watchlist_seed",
            headers={"X-Internal-Token": VALID_TOKEN},
            json={"bundle_ids": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]},
            params={"pack_id": "not-a-uuid"},
        )
        assert response.status_code == 422
        data = response.json()
        assert "pack_id" in data.get("detail", "").lower()
