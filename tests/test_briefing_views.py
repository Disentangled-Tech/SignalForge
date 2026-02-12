"""Tests for briefing page HTML routes."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure env vars are set before importing app modules
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://localhost:5432/signalforge_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("INTERNAL_JOB_TOKEN", "test-internal-token")

from app.api.briefing_views import router  # noqa: E402
from app.api.deps import get_db, require_ui_auth  # noqa: E402
from app.models.analysis_record import AnalysisRecord  # noqa: E402
from app.models.briefing_item import BriefingItem  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.user import User  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────


def _make_user() -> MagicMock:
    """Create a mock User."""
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "testuser"
    return user


def _make_company(id: int = 1, **overrides) -> MagicMock:
    """Create a mock Company."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=id, name="Acme Corp", website_url="https://acme.example.com",
        founder_name="Jane Doe", founder_linkedin_url=None,
        company_linkedin_url=None, source="manual",
        target_profile_match=False, current_stage="mvp_building",
        notes=None, cto_need_score=85, created_at=now,
        updated_at=now, last_scan_at=None,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=Company)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_analysis(id: int = 1, **overrides) -> MagicMock:
    """Create a mock AnalysisRecord."""
    defaults = dict(
        id=id, company_id=1, source_type="full_analysis",
        stage="mvp_building", stage_confidence=80,
        pain_signals_json={}, evidence_bullets=[],
        explanation="Test explanation",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    mock = MagicMock(spec=AnalysisRecord)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_briefing_item(id: int = 1, **overrides) -> MagicMock:
    """Create a mock BriefingItem with company and analysis."""
    company = overrides.pop("company", _make_company())
    analysis = overrides.pop("analysis", _make_analysis())
    defaults = dict(
        id=id, company_id=company.id, analysis_id=analysis.id,
        why_now="Recent funding round",
        risk_summary="Early stage, may not convert",
        suggested_angle="Technical advisor for scaling",
        outreach_subject="Congrats on the raise",
        outreach_message="Hi Jane, I noticed your company just raised.",
        briefing_date=date.today(),
        created_at=datetime.now(timezone.utc),
        company=company, analysis=analysis,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=BriefingItem)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _create_test_app(mock_db, mock_user=None):
    """Create a FastAPI app with briefing router and mocked deps."""
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    if mock_user is not None:
        app.dependency_overrides[require_ui_auth] = lambda: mock_user

    return app


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def mock_user():
    return _make_user()


@pytest.fixture
def auth_client(mock_db, mock_user):
    """Authenticated test client with mocked DB."""
    app = _create_test_app(mock_db, mock_user)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def noauth_client(mock_db):
    """Unauthenticated test client — no auth override."""
    app = _create_test_app(mock_db)
    return TestClient(app, raise_server_exceptions=False)


# ── Tests ────────────────────────────────────────────────────────────


class TestBriefingPage:
    """Tests for GET /briefing."""

    def test_briefing_renders_with_items(self, mock_db, mock_user):
        """Briefing page renders when items exist."""
        item = _make_briefing_item()
        query_mock = MagicMock()
        query_mock.options.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.join.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.all.return_value = [item]
        mock_db.query.return_value = query_mock

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Acme Corp" in resp.text
        assert "Jane Doe" in resp.text
        assert "Daily Briefing" in resp.text
        assert "Congrats on the raise" in resp.text
        assert "Copy Outreach" in resp.text

    def test_briefing_empty_state(self, mock_db, mock_user):
        """Briefing page shows empty state when no items."""
        query_mock = MagicMock()
        query_mock.options.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.join.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.all.return_value = []
        mock_db.query.return_value = query_mock

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "No briefing" in resp.text
        assert "Generate Now" in resp.text

    def test_briefing_multiple_items_ordered(self, mock_db, mock_user):
        """Briefing page renders multiple items."""
        co1 = _make_company(id=1, name="Alpha Co", cto_need_score=90)
        co2 = _make_company(id=2, name="Beta Co", cto_need_score=60)
        item1 = _make_briefing_item(id=1, company=co1)
        item2 = _make_briefing_item(id=2, company=co2)

        query_mock = MagicMock()
        query_mock.options.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.join.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.all.return_value = [item1, item2]
        mock_db.query.return_value = query_mock

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Alpha Co" in resp.text
        assert "Beta Co" in resp.text


class TestBriefingByDate:
    """Tests for GET /briefing/{date_str}."""

    def test_date_specific_briefing(self, mock_db, mock_user):
        """Briefing page renders for a specific date."""
        target = date(2026, 1, 15)
        item = _make_briefing_item(briefing_date=target)

        query_mock = MagicMock()
        query_mock.options.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.join.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.all.return_value = [item]
        mock_db.query.return_value = query_mock

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing/2026-01-15")

        assert resp.status_code == 200
        assert "January 15, 2026" in resp.text

    def test_invalid_date_redirects(self, mock_db, mock_user):
        """Invalid date string redirects to /briefing."""
        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing/not-a-date", follow_redirects=False)

        assert resp.status_code == 302
        assert "/briefing" in resp.headers["location"]


class TestBriefingGenerate:
    """Tests for POST /briefing/generate."""

    def test_generate_calls_service_and_redirects(self, mock_db, mock_user):
        """Generate endpoint calls briefing service and redirects."""
        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("app.api.briefing_views.generate_briefing", create=True) as mock_gen:
            # Patch the import inside the route
            with patch.dict("sys.modules", {"app.services.briefing": MagicMock(generate_briefing=mock_gen)}):
                resp = client.post("/briefing/generate", follow_redirects=False)

        assert resp.status_code == 303
        assert "/briefing" in resp.headers["location"]

    def test_generate_import_error_redirects_with_error(self, mock_db, mock_user):
        """When service not available, redirects with error."""
        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)

        # Ensure the import fails by removing the module
        import sys
        saved = sys.modules.pop("app.services.briefing", None)
        try:
            with patch.dict("sys.modules", {"app.services.briefing": None}):
                # This should cause ImportError when route tries to import
                resp = client.post("/briefing/generate", follow_redirects=False)
        finally:
            if saved is not None:
                sys.modules["app.services.briefing"] = saved

        assert resp.status_code == 303
        assert "error" in resp.headers["location"]


class TestAuthRequired:
    """Tests that routes require authentication."""

    def test_briefing_requires_auth(self, noauth_client):
        """GET /briefing redirects to login without authentication."""
        resp = noauth_client.get("/briefing", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"

    def test_briefing_date_requires_auth(self, noauth_client):
        """GET /briefing/{date} redirects to login without authentication."""
        resp = noauth_client.get("/briefing/2026-01-01", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"

    def test_generate_requires_auth(self, noauth_client):
        """POST /briefing/generate redirects to login without authentication."""
        resp = noauth_client.post("/briefing/generate", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"
