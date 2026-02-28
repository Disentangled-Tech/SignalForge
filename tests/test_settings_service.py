"""Tests for the settings service functions."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.models.app_settings import AppSettings
from app.models.operator_profile import OperatorProfile
from app.services.settings_service import (
    get_app_settings,
    get_operator_profile,
    update_app_settings,
    update_operator_profile,
)

# ── get_app_settings ─────────────────────────────────────────────────


class TestGetAppSettings:
    """Tests for get_app_settings()."""

    def test_returns_dict_from_db_rows(self) -> None:
        row1 = MagicMock(spec=AppSettings)
        row1.key = "briefing_time"
        row1.value = "08:00"
        row2 = MagicMock(spec=AppSettings)
        row2.key = "briefing_email"
        row2.value = "test@example.com"

        db = MagicMock()
        db.query.return_value.all.return_value = [row1, row2]

        result = get_app_settings(db)
        assert result == {"briefing_time": "08:00", "briefing_email": "test@example.com"}

    def test_returns_empty_dict_when_no_rows(self) -> None:
        db = MagicMock()
        db.query.return_value.all.return_value = []

        result = get_app_settings(db)
        assert result == {}

    def test_includes_none_values(self) -> None:
        row = MagicMock(spec=AppSettings)
        row.key = "scoring_weights"
        row.value = None

        db = MagicMock()
        db.query.return_value.all.return_value = [row]

        result = get_app_settings(db)
        assert result == {"scoring_weights": None}


# ── update_app_settings ──────────────────────────────────────────────


class TestUpdateAppSettings:
    """Tests for update_app_settings()."""

    def test_creates_new_row_when_key_missing(self) -> None:
        db = MagicMock()
        # filter().first() returns None → key doesn't exist
        db.query.return_value.filter.return_value.first.return_value = None
        # After commit, get_app_settings returns updated dict
        db.query.return_value.all.return_value = []

        update_app_settings(db, {"briefing_time": "09:00"})

        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_updates_existing_row(self) -> None:
        existing = MagicMock(spec=AppSettings)
        existing.key = "briefing_time"
        existing.value = "08:00"

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing
        db.query.return_value.all.return_value = []

        update_app_settings(db, {"briefing_time": "10:00"})

        assert existing.value == "10:00"
        db.commit.assert_called_once()
        # Should NOT call db.add for existing rows
        db.add.assert_not_called()

    def test_upserts_multiple_keys(self) -> None:
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.all.return_value = []

        update_app_settings(db, {"key1": "val1", "key2": "val2"})

        assert db.add.call_count == 2
        db.commit.assert_called_once()


# ── get_operator_profile ─────────────────────────────────────────────


class TestGetOperatorProfile:
    """Tests for get_operator_profile()."""

    def test_returns_content_when_exists(self) -> None:
        row = MagicMock(spec=OperatorProfile)
        row.content = "# My Profile\nFractional CTO"

        db = MagicMock()
        db.query.return_value.first.return_value = row

        result = get_operator_profile(db)
        assert result == "# My Profile\nFractional CTO"

    def test_returns_empty_string_when_no_row(self) -> None:
        db = MagicMock()
        db.query.return_value.first.return_value = None

        result = get_operator_profile(db)
        assert result == ""

    def test_returns_empty_string_when_content_is_none(self) -> None:
        row = MagicMock(spec=OperatorProfile)
        row.content = None

        db = MagicMock()
        db.query.return_value.first.return_value = row

        result = get_operator_profile(db)
        assert result == ""


# ── update_operator_profile ──────────────────────────────────────────


class TestUpdateOperatorProfile:
    """Tests for update_operator_profile()."""

    def test_creates_profile_when_none_exists(self) -> None:
        db = MagicMock()
        db.query.return_value.first.return_value = None

        update_operator_profile(db, "# New Profile")

        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    def test_updates_existing_profile(self) -> None:
        existing = MagicMock(spec=OperatorProfile)
        existing.content = "# Old Profile"

        db = MagicMock()
        db.query.return_value.first.return_value = existing

        result = update_operator_profile(db, "# Updated Profile")

        assert existing.content == "# Updated Profile"
        db.add.assert_not_called()
        db.commit.assert_called_once()
        db.refresh.assert_called_once()
