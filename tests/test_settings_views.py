"""Tests for settings page HTML routes (issue #27: recent job runs)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db, require_ui_auth
from app.api.settings_views import router
from app.models.job_run import JobRun
from app.models.user import User


def _make_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "testuser"
    return user


def _make_job_run(**overrides) -> MagicMock:
    defaults = dict(
        id=1,
        job_type="briefing",
        status="completed",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        companies_processed=3,
        company_id=None,
        error_message=None,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=JobRun)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _create_test_app(mock_db, mock_user=None):
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    if mock_user is not None:
        app.dependency_overrides[require_ui_auth] = lambda: mock_user

    return app


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_user():
    return _make_user()


class TestSettingsPage:
    def test_settings_returns_200_with_recent_jobs(
        self, mock_db, mock_user
    ):
        """GET /settings shows Recent Job Runs table when jobs exist (issue #27)."""
        job1 = _make_job_run(id=1, job_type="briefing", status="completed")
        job2 = _make_job_run(
            id=2, job_type="scan", status="failed", error_message="Network timeout"
        )

        # get_app_settings: db.query(AppSettings).all()
        settings_rows = [
            MagicMock(key="briefing_time", value="08:00"),
            MagicMock(key="briefing_email", value=""),
            MagicMock(key="scoring_weights", value="{}"),
        ]
        # JobRun: db.query(JobRun).order_by().limit(20).all()
        base = mock_db.query.return_value
        base.all.return_value = settings_rows
        base.order_by.return_value.limit.return_value.all.return_value = [
            job1,
            job2,
        ]

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app)

        resp = client.get("/settings")

        assert resp.status_code == 200
        assert "Recent Job Runs" in resp.text
        assert "briefing" in resp.text
        assert "scan" in resp.text
        assert "completed" in resp.text
        assert "failed" in resp.text
        assert "Network timeout" in resp.text

    def test_settings_shows_empty_state_when_no_jobs(
        self, mock_db, mock_user
    ):
        """GET /settings shows empty state when no job runs exist."""
        settings_rows = [
            MagicMock(key="briefing_time", value="08:00"),
            MagicMock(key="briefing_email", value=""),
            MagicMock(key="scoring_weights", value="{}"),
        ]
        base = mock_db.query.return_value
        base.all.return_value = settings_rows
        base.order_by.return_value.limit.return_value.all.return_value = []

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app)

        resp = client.get("/settings")

        assert resp.status_code == 200
        assert "No job runs yet" in resp.text
