"""Tests for settings resolver (issue #29)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.settings_resolver import (
    ResolvedSettings,
    get_resolved_settings,
)


def _make_settings_row(key: str, value: str):
    row = MagicMock()
    row.key = key
    row.value = value
    return row


class TestGetResolvedSettings:
    """Tests for get_resolved_settings()."""

    def test_uses_app_settings_over_env(self) -> None:
        """AppSettings values override env when present."""
        db = MagicMock()
        db.query.return_value.all.return_value = [
            _make_settings_row("briefing_time", "09:30"),
            _make_settings_row("briefing_email", "ops@example.com"),
            _make_settings_row("briefing_email_enabled", "true"),
        ]

        with patch("app.services.settings_resolver.get_settings") as mock_get:
            env = MagicMock()
            env.briefing_time = "08:00"
            env.briefing_email_to = ""
            env.briefing_email_enabled = False
            env.smtp_host = ""
            env.smtp_port = 587
            env.smtp_user = ""
            env.smtp_password = ""
            env.smtp_from = ""
            mock_get.return_value = env

            result = get_resolved_settings(db)

        assert result.briefing_time == "09:30"
        assert result.briefing_email == "ops@example.com"
        assert result.briefing_email_enabled is True

    def test_falls_back_to_env_when_key_missing(self) -> None:
        """When AppSettings has no briefing_time, use env."""
        db = MagicMock()
        db.query.return_value.all.return_value = []

        with patch("app.services.settings_resolver.get_settings") as mock_get:
            env = MagicMock()
            env.briefing_time = "07:00"
            env.briefing_email_to = "default@example.com"
            env.briefing_email_enabled = True
            env.smtp_host = "smtp.example.com"
            env.smtp_port = 587
            env.smtp_user = ""
            env.smtp_password = ""
            env.smtp_from = "noreply@example.com"
            mock_get.return_value = env

            result = get_resolved_settings(db)

        assert result.briefing_time == "07:00"
        assert result.briefing_email == "default@example.com"
        assert result.briefing_email_enabled is True

    def test_briefing_frequency_daily_by_default(self) -> None:
        """briefing_frequency defaults to daily when missing."""
        db = MagicMock()
        db.query.return_value.all.return_value = []

        with patch("app.services.settings_resolver.get_settings") as mock_get:
            env = MagicMock()
            env.briefing_time = "08:00"
            env.briefing_email_to = ""
            env.briefing_email_enabled = False
            env.smtp_host = ""
            env.smtp_port = 587
            env.smtp_user = ""
            env.smtp_password = ""
            env.smtp_from = ""
            mock_get.return_value = env

            result = get_resolved_settings(db)

        assert result.briefing_frequency == "daily"
        assert result.briefing_day_of_week == 0

    def test_briefing_frequency_weekly_from_db(self) -> None:
        """briefing_frequency and briefing_day_of_week from AppSettings."""
        db = MagicMock()
        db.query.return_value.all.return_value = [
            _make_settings_row("briefing_frequency", "weekly"),
            _make_settings_row("briefing_day_of_week", "2"),  # Wednesday
        ]

        with patch("app.services.settings_resolver.get_settings") as mock_get:
            env = MagicMock()
            env.briefing_time = "08:00"
            env.briefing_email_to = ""
            env.briefing_email_enabled = False
            env.smtp_host = ""
            env.smtp_port = 587
            env.smtp_user = ""
            env.smtp_password = ""
            env.smtp_from = ""
            mock_get.return_value = env

            result = get_resolved_settings(db)

        assert result.briefing_frequency == "weekly"
        assert result.briefing_day_of_week == 2


class TestResolvedSettings:
    """Tests for ResolvedSettings helper methods."""

    def test_should_send_briefing_email_true_when_all_set(self) -> None:
        s = ResolvedSettings(
            briefing_time="08:00",
            briefing_email="ops@example.com",
            briefing_email_enabled=True,
            briefing_frequency="daily",
            briefing_day_of_week=0,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="",
            smtp_password="",
            smtp_from="noreply@example.com",
        )
        assert s.should_send_briefing_email() is True

    def test_should_send_briefing_email_false_when_disabled(self) -> None:
        s = ResolvedSettings(
            briefing_time="08:00",
            briefing_email="ops@example.com",
            briefing_email_enabled=False,
            briefing_frequency="daily",
            briefing_day_of_week=0,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="",
            smtp_password="",
            smtp_from="noreply@example.com",
        )
        assert s.should_send_briefing_email() is False

    def test_should_send_briefing_email_false_when_no_recipient(self) -> None:
        s = ResolvedSettings(
            briefing_time="08:00",
            briefing_email="",
            briefing_email_enabled=True,
            briefing_frequency="daily",
            briefing_day_of_week=0,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="",
            smtp_password="",
            smtp_from="noreply@example.com",
        )
        assert s.should_send_briefing_email() is False

    def test_should_send_briefing_email_false_when_no_smtp(self) -> None:
        s = ResolvedSettings(
            briefing_time="08:00",
            briefing_email="ops@example.com",
            briefing_email_enabled=True,
            briefing_frequency="daily",
            briefing_day_of_week=0,
            smtp_host="",
            smtp_port=587,
            smtp_user="",
            smtp_password="",
            smtp_from="",
        )
        assert s.should_send_briefing_email() is False
