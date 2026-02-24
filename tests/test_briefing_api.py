"""Tests for briefing JSON API (Issue #110)."""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_constants import TEST_SECRET_KEY, TEST_USERNAME_VIEWS

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://localhost:5432/signalforge_test")
os.environ.setdefault("SECRET_KEY", TEST_SECRET_KEY)

from app.api.briefing import router  # noqa: E402
from app.api.deps import get_db, require_auth  # noqa: E402


def _make_user():
    """Create a mock User."""
    user = MagicMock()
    user.id = 1
    user.username = TEST_USERNAME_VIEWS
    return user


def _create_app(mock_db, mock_user=None):
    """Create FastAPI app with briefing API router."""
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    if mock_user is not None:
        app.dependency_overrides[require_auth] = lambda: mock_user
    return app


@patch("app.api.briefing.get_briefing_data")
def test_get_briefing_daily_returns_json(mock_get_data):
    """GET /api/briefing/daily returns 200 with valid schema."""
    mock_get_data.return_value = {
        "items": [],
        "emerging_companies": [],
        "display_scores": {},
        "esl_by_company": {},
    }
    app = _create_app(MagicMock(), _make_user())
    client = TestClient(app)
    resp = client.get("/daily")
    assert resp.status_code == 200
    data = resp.json()
    assert "date" in data
    assert "items" in data
    assert "emerging_companies" in data
    assert "total" in data
    assert data["total"] == 0


@patch("app.api.briefing.get_briefing_data")
def test_briefing_json_requires_auth(mock_get_data):
    """GET /api/briefing/daily without auth returns 401."""
    mock_get_data.return_value = {
        "items": [],
        "emerging_companies": [],
        "display_scores": {},
        "esl_by_company": {},
    }
    app = _create_app(MagicMock())  # no auth override
    client = TestClient(app)
    resp = client.get("/daily")
    assert resp.status_code == 401


@patch("app.api.briefing.get_briefing_data")
def test_briefing_json_date_param(mock_get_data):
    """GET /api/briefing/daily?date=YYYY-MM-DD filters by date."""
    mock_get_data.return_value = {
        "items": [],
        "emerging_companies": [],
        "display_scores": {},
        "esl_by_company": {},
    }
    app = _create_app(MagicMock(), _make_user())
    client = TestClient(app)
    resp = client.get("/daily?date=2026-01-15")
    assert resp.status_code == 200
    assert resp.json()["date"] == "2026-01-15"
    mock_get_data.assert_called_once()
    call_args = mock_get_data.call_args[0]
    assert call_args[1] == date(2026, 1, 15)


@patch("app.api.briefing.get_settings")
@patch("app.api.briefing.get_briefing_data")
def test_briefing_json_invalid_workspace_id_returns_422(mock_get_data, mock_settings):
    """When multi_workspace_enabled and workspace_id invalid, return 422."""
    mock_settings.return_value = MagicMock(multi_workspace_enabled=True)
    mock_get_data.return_value = {
        "items": [],
        "emerging_companies": [],
        "display_scores": {},
        "esl_by_company": {},
    }
    app = _create_app(MagicMock(), _make_user())
    client = TestClient(app)
    resp = client.get("/daily?workspace_id=not-a-uuid")
    assert resp.status_code == 422
    assert "workspace_id" in resp.json().get("detail", "").lower()
    mock_get_data.assert_not_called()


@patch("app.api.briefing.get_settings")
@patch("app.api.briefing.get_briefing_data")
def test_briefing_json_multi_workspace_scopes_by_workspace_id(mock_get_data, mock_settings):
    """When multi_workspace_enabled and valid workspace_id, get_briefing_data called with it."""
    mock_settings.return_value = MagicMock(multi_workspace_enabled=True)
    mock_get_data.return_value = {
        "items": [],
        "emerging_companies": [],
        "display_scores": {},
        "esl_by_company": {},
    }
    app = _create_app(MagicMock(), _make_user())
    client = TestClient(app)
    ws_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    resp = client.get(f"/daily?workspace_id={ws_uuid}")
    assert resp.status_code == 200
    mock_get_data.assert_called_once()
    call_kwargs = mock_get_data.call_args[1]
    assert call_kwargs["workspace_id"] == ws_uuid
