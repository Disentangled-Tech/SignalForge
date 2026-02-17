"""Tests for settings page HTML routes (issue #27, #29)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

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

    def test_settings_shows_briefing_frequency_field(self, mock_db, mock_user):
        """GET /settings shows briefing frequency and day-of-week (issue #29)."""
        settings_rows = [
            MagicMock(key="briefing_time", value="08:00"),
            MagicMock(key="briefing_email", value=""),
            MagicMock(key="briefing_frequency", value="weekly"),
            MagicMock(key="briefing_day_of_week", value="2"),
        ]
        base = mock_db.query.return_value
        base.all.return_value = settings_rows
        base.order_by.return_value.limit.return_value.all.return_value = []

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app)

        resp = client.get("/settings")

        assert resp.status_code == 200
        assert "Briefing Frequency" in resp.text
        assert "Daily" in resp.text
        assert "Weekly" in resp.text
        assert "Wednesday" in resp.text
        assert "Enable briefing email" in resp.text

    def test_settings_shows_scan_change_rate_when_available(
        self, mock_db, mock_user
    ):
        """GET /settings shows Scan Change Rate card when metric available (issue #61)."""
        settings_rows = [
            MagicMock(key="briefing_time", value="08:00"),
            MagicMock(key="briefing_email", value=""),
        ]
        base = mock_db.query.return_value
        base.all.return_value = settings_rows
        base.order_by.return_value.limit.return_value.all.return_value = []

        with patch(
            "app.api.settings_views.get_scan_change_rate_30d"
        ) as mock_scan_metrics:
            mock_scan_metrics.return_value = (20.0, 10, 50)

            app = _create_test_app(mock_db, mock_user)
            client = TestClient(app)

            resp = client.get("/settings")

        assert resp.status_code == 200
        assert "Scan Change Rate (Last 30 Days)" in resp.text
        assert "20.0%" in resp.text
        assert "10" in resp.text
        assert "50" in resp.text
        assert "tune cron frequency" in resp.text

    def test_settings_shows_no_scan_data_when_empty(
        self, mock_db, mock_user
    ):
        """GET /settings shows empty state when no scan data (issue #61)."""
        settings_rows = [
            MagicMock(key="briefing_time", value="08:00"),
            MagicMock(key="briefing_email", value=""),
        ]
        base = mock_db.query.return_value
        base.all.return_value = settings_rows
        base.order_by.return_value.limit.return_value.all.return_value = []

        with patch(
            "app.api.settings_views.get_scan_change_rate_30d"
        ) as mock_scan_metrics:
            mock_scan_metrics.return_value = (None, 0, 0)

            app = _create_test_app(mock_db, mock_user)
            client = TestClient(app)

            resp = client.get("/settings")

        assert resp.status_code == 200
        assert "Scan Change Rate (Last 30 Days)" in resp.text
        assert "No scan data in last 30 days" in resp.text


class TestSettingsSave:
    """Tests for POST /settings (issue #29)."""

    def test_post_saves_briefing_frequency_weekly(self, mock_db, mock_user):
        """POST with briefing_frequency=weekly updates AppSettings."""
        settings_rows = [
            MagicMock(key="briefing_time", value="08:00"),
            MagicMock(key="briefing_email", value=""),
        ]
        base = mock_db.query.return_value
        base.all.return_value = settings_rows
        base.order_by.return_value.limit.return_value.all.return_value = []
        base.filter.return_value.first.return_value = None

        with patch(
            "app.api.settings_views.update_app_settings"
        ) as mock_update:
            mock_update.return_value = {}

            app = _create_test_app(mock_db, mock_user)
            client = TestClient(app, follow_redirects=False)

            resp = client.post(
                "/settings",
                data={
                    "briefing_time": "09:00",
                    "briefing_email": "ops@example.com",
                    "briefing_email_enabled": "on",
                    "briefing_frequency": "weekly",
                    "briefing_day_of_week": "3",
                    "scoring_weights": "{}",
                },
            )

        assert resp.status_code == 303
        assert "success" in resp.headers.get("location", "")
        mock_update.assert_called_once()
        updates = mock_update.call_args[0][1]
        assert updates.get("briefing_frequency") == "weekly"
        assert updates.get("briefing_day_of_week") == "3"
        assert updates.get("briefing_email_enabled") == "true"

    def test_post_empty_briefing_time_redirects_with_error(self, mock_db, mock_user):
        """POST with empty briefing_time redirects with error (required field)."""
        settings_rows = [MagicMock(key="briefing_time", value="08:00")]
        base = mock_db.query.return_value
        base.all.return_value = settings_rows
        base.order_by.return_value.limit.return_value.all.return_value = []

        with patch(
            "app.api.settings_views.update_app_settings"
        ) as mock_update:
            app = _create_test_app(mock_db, mock_user)
            client = TestClient(app, follow_redirects=False)

            resp = client.post(
                "/settings",
                data={
                    "briefing_time": "",
                    "briefing_email": "",
                    "briefing_email_enabled": "",
                    "briefing_frequency": "daily",
                    "briefing_day_of_week": "0",
                    "scoring_weights": "{}",
                },
            )

        assert resp.status_code == 303
        assert "error" in resp.headers.get("location", "")
        assert "Briefing+time+is+required" in resp.headers.get("location", "")
        mock_update.assert_not_called()

    def test_post_invalid_briefing_time_redirects_with_error(self, mock_db, mock_user):
        """POST with invalid briefing_time (e.g. 25:00) redirects with error."""
        settings_rows = [MagicMock(key="briefing_time", value="08:00")]
        base = mock_db.query.return_value
        base.all.return_value = settings_rows
        base.order_by.return_value.limit.return_value.all.return_value = []

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, follow_redirects=False)

        resp = client.post(
            "/settings",
            data={
                "briefing_time": "25:00",
                "briefing_email": "",
                "briefing_email_enabled": "",
                "briefing_frequency": "daily",
                "briefing_day_of_week": "0",
                "scoring_weights": "{}",
            },
        )

        assert resp.status_code == 303
        assert "error" in resp.headers.get("location", "")
        assert "Invalid" in resp.headers.get("location", "")

    def test_post_allows_clearing_briefing_email(self, mock_db, mock_user):
        """POST with empty briefing_email clears the setting (issue #29)."""
        settings_rows = [
            MagicMock(key="briefing_email", value="old@example.com"),
        ]
        base = mock_db.query.return_value
        base.all.return_value = settings_rows
        base.order_by.return_value.limit.return_value.all.return_value = []
        base.filter.return_value.first.return_value = MagicMock(value="old@example.com")

        with patch(
            "app.api.settings_views.update_app_settings"
        ) as mock_update:
            mock_update.return_value = {}

            app = _create_test_app(mock_db, mock_user)
            client = TestClient(app, follow_redirects=False)

            resp = client.post(
                "/settings",
                data={
                    "briefing_time": "08:00",
                    "briefing_email": "",
                    "briefing_email_enabled": "",
                    "briefing_frequency": "daily",
                    "briefing_day_of_week": "0",
                    "scoring_weights": "{}",
                },
            )

        assert resp.status_code == 303
        mock_update.assert_called_once()
        updates = mock_update.call_args[0][1]
        assert updates.get("briefing_email") == ""

    def test_post_invalid_email_redirects_with_error(self, mock_db, mock_user):
        """POST with invalid email format redirects with error."""
        settings_rows = [MagicMock(key="briefing_time", value="08:00")]
        base = mock_db.query.return_value
        base.all.return_value = settings_rows
        base.order_by.return_value.limit.return_value.all.return_value = []

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, follow_redirects=False)

        resp = client.post(
            "/settings",
            data={
                "briefing_time": "08:00",
                "briefing_email": "not-an-email",
                "briefing_email_enabled": "",
                "briefing_frequency": "daily",
                "briefing_day_of_week": "0",
                "scoring_weights": "{}",
            },
        )

        assert resp.status_code == 303
        assert "error" in resp.headers.get("location", "")


class TestProfilePage:
    """Tests for GET /settings/profile (issue #30)."""

    def test_profile_returns_200_with_content(self, mock_db, mock_user):
        """GET /settings/profile returns 200, shows textarea, pre-fills profile_content."""
        with patch(
            "app.api.settings_views.get_operator_profile"
        ) as mock_get_profile:
            mock_get_profile.return_value = "# My Profile\n15 years CTO experience"

            app = _create_test_app(mock_db, mock_user)
            client = TestClient(app)

            resp = client.get("/settings/profile")

        assert resp.status_code == 200
        assert "Operator Profile" in resp.text
        assert "Profile Content (Markdown)" in resp.text
        assert "My Profile" in resp.text
        assert "15 years CTO experience" in resp.text
        mock_get_profile.assert_called_once()


class TestProfileSave:
    """Tests for POST /settings/profile (issue #30)."""

    def test_profile_save_updates_and_redirects(self, mock_db, mock_user):
        """POST with content calls update_operator_profile and redirects with success."""
        with patch(
            "app.api.settings_views.update_operator_profile"
        ) as mock_update:
            app = _create_test_app(mock_db, mock_user)
            client = TestClient(app, follow_redirects=False)

            resp = client.post(
                "/settings/profile",
                data={"content": "# Updated Profile\nNew content here"},
            )

        assert resp.status_code == 303
        assert resp.headers.get("location") == "/settings/profile?success=Profile+saved"
        mock_update.assert_called_once_with(mock_db, "# Updated Profile\nNew content here")

    def test_profile_save_allows_empty(self, mock_db, mock_user):
        """POST with empty content is accepted (clears profile)."""
        with patch(
            "app.api.settings_views.update_operator_profile"
        ) as mock_update:
            app = _create_test_app(mock_db, mock_user)
            client = TestClient(app, follow_redirects=False)

            resp = client.post(
                "/settings/profile",
                data={"content": ""},
            )

        assert resp.status_code == 303
        mock_update.assert_called_once_with(mock_db, "")

    def test_profile_save_rejects_content_too_long(self, mock_db, mock_user):
        """POST with content exceeding 50KB redirects with error."""
        with patch(
            "app.api.settings_views.update_operator_profile"
        ) as mock_update:
            app = _create_test_app(mock_db, mock_user)
            client = TestClient(app, follow_redirects=False)

            resp = client.post(
                "/settings/profile",
                data={"content": "x" * 50_001},
            )

        assert resp.status_code == 303
        assert "error" in resp.headers.get("location", "")
        assert "Profile+content+too+long" in resp.headers.get("location", "")
        mock_update.assert_not_called()
