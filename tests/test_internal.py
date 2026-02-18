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

