"""Tests for HTML-serving view routes."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.analysis_record import AnalysisRecord
from app.models.briefing_item import BriefingItem
from app.models.signal_record import SignalRecord
from app.models.user import User


# ── Helpers ──────────────────────────────────────────────────────────


def _make_user(username: str = "admin", password: str = "secret123") -> User:
    """Create a User with a hashed password (no DB)."""
    user = User(id=1, username=username)
    user.set_password(password)
    return user


def _make_mock_company(**overrides):
    """Return a MagicMock Company for use in templates."""
    from app.models.company import Company

    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, name="Acme Corp", website_url="https://acme.example.com",
        founder_name="Jane Doe", founder_linkedin_url=None,
        company_linkedin_url=None, source="manual",
        target_profile_match=False, current_stage="scaling_team",
        notes=None, cto_need_score=75,
        created_at=now, updated_at=now, last_scan_at=now,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=Company)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_company_read(**overrides):
    """Return a CompanyRead schema instance for template rendering."""
    from app.schemas.company import CompanyRead

    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, company_name="Acme Corp", website_url="https://acme.example.com",
        founder_name="Jane Doe", founder_linkedin_url=None,
        company_linkedin_url=None, source="manual",
        target_profile_match=None, current_stage="scaling_team",
        notes=None, cto_need_score=75,
        created_at=now, updated_at=now, last_scan_at=now,
    )
    defaults.update(overrides)
    return CompanyRead(**defaults)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_db_session():
    """A reusable mock DB session."""
    return MagicMock()


@pytest.fixture
def test_user():
    """A test user instance."""
    return _make_user()


@pytest.fixture
def views_client(mock_db_session, test_user):
    """TestClient with mocked DB and auth for view routes."""
    from app.db.session import get_db
    from app.api.views import _require_ui_auth
    from app.main import create_app

    app = create_app()

    def override_get_db():
        yield mock_db_session

    def override_auth():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_require_ui_auth] = override_auth
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def noauth_client(mock_db_session):
    """TestClient with mocked DB but NO auth override (unauthenticated)."""
    from app.db.session import get_db
    from app.main import create_app

    app = create_app()

    def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


# ── Login page tests ────────────────────────────────────────────────


class TestLoginPage:
    def test_login_page_renders(self, noauth_client):
        resp = noauth_client.get("/login")
        assert resp.status_code == 200
        assert "Sign In" in resp.text
        assert "username" in resp.text
        assert "password" in resp.text

    def test_login_post_invalid_creds(self, noauth_client, mock_db_session):
        """POST /login with bad credentials shows error."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        resp = noauth_client.post(
            "/login", data={"username": "bad", "password": "bad"},
            follow_redirects=False,
        )
        assert resp.status_code == 401
        assert "Invalid" in resp.text

    def test_login_post_valid_creds_redirects(self, noauth_client, mock_db_session, test_user):
        """POST /login with valid credentials sets cookie and redirects."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = test_user
        resp = noauth_client.post(
            "/login", data={"username": "admin", "password": "secret123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/companies" in resp.headers.get("location", "")


# ── Companies list tests ────────────────────────────────────────────


class TestCompaniesList:
    def test_companies_list_requires_auth(self, noauth_client):
        """GET /companies without auth redirects to login."""
        resp = noauth_client.get("/companies", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"

    @patch("app.api.views.list_companies")
    def test_companies_list_renders(self, mock_list, views_client):
        """GET /companies renders a table with company data."""
        company = _make_company_read(company_name="TestCo", cto_need_score=85)
        mock_list.return_value = ([company], 1)
        resp = views_client.get("/companies")
        assert resp.status_code == 200
        assert "TestCo" in resp.text
        assert "85" in resp.text

    @patch("app.api.views.list_companies")
    def test_companies_list_empty(self, mock_list, views_client):
        """GET /companies with no data shows empty state."""
        mock_list.return_value = ([], 0)
        resp = views_client.get("/companies")
        assert resp.status_code == 200
        assert "No companies found" in resp.text

    @patch("app.api.views.list_companies")
    def test_companies_list_search(self, mock_list, views_client):
        """GET /companies?search=foo passes search param."""
        mock_list.return_value = ([], 0)
        resp = views_client.get("/companies?search=foo")
        assert resp.status_code == 200
        mock_list.assert_called_once()
        call_kwargs = mock_list.call_args
        assert call_kwargs[1].get("search") == "foo" or call_kwargs.kwargs.get("search") == "foo"


# ── Add company tests ───────────────────────────────────────────────


class TestAddCompany:
    def test_add_form_renders(self, views_client):
        """GET /companies/add renders the form."""
        resp = views_client.get("/companies/add")
        assert resp.status_code == 200
        assert "Add Company" in resp.text
        assert "company_name" in resp.text

    def test_add_form_requires_auth(self, noauth_client):
        """GET /companies/add without auth redirects to login."""
        resp = noauth_client.get("/companies/add", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"

    @patch("app.api.views.create_company")
    def test_add_company_success(self, mock_create, views_client):
        """POST /companies/add with valid data redirects."""
        mock_create.return_value = _make_company_read()
        resp = views_client.post(
            "/companies/add",
            data={"company_name": "New Co", "source": "manual"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/companies" in resp.headers.get("location", "")
        mock_create.assert_called_once()

    def test_add_company_validation_error(self, views_client):
        """POST /companies/add with empty name shows error."""
        resp = views_client.post(
            "/companies/add",
            data={"company_name": "", "source": "manual"},
        )
        assert resp.status_code == 422
        assert "required" in resp.text.lower()


# ── Import company tests ──────────────────────────────────────────


class TestImportCompanies:
    def test_import_page_renders(self, views_client):
        """GET /companies/import renders the import form."""
        resp = views_client.get("/companies/import")
        assert resp.status_code == 200
        assert "Import Companies" in resp.text
        assert "csv_file" in resp.text
        assert "json_data" in resp.text

    def test_import_page_requires_auth(self, noauth_client):
        """GET /companies/import without auth redirects to login."""
        resp = noauth_client.get("/companies/import", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"

    @patch("app.api.views.bulk_import_companies")
    def test_csv_import(self, mock_import, views_client):
        """POST /companies/import with CSV file processes correctly."""
        from app.schemas.company import BulkImportResponse, BulkImportRow

        mock_import.return_value = BulkImportResponse(
            total=2, created=2, duplicates=0, errors=0,
            rows=[
                BulkImportRow(row=1, company_name="Acme Corp", status="created"),
                BulkImportRow(row=2, company_name="Beta Inc", status="created"),
            ],
        )
        csv_content = "company_name,website_url\nAcme Corp,https://acme.example.com\nBeta Inc,https://beta.example.com\n"
        resp = views_client.post(
            "/companies/import",
            files={"csv_file": ("companies.csv", csv_content, "text/csv")},
            data={"json_data": ""},
        )
        assert resp.status_code == 200
        mock_import.assert_called_once()
        assert "Acme Corp" in resp.text
        assert "Created" in resp.text

    @patch("app.api.views.bulk_import_companies")
    def test_json_import(self, mock_import, views_client):
        """POST /companies/import with JSON data processes correctly."""
        from app.schemas.company import BulkImportResponse, BulkImportRow

        mock_import.return_value = BulkImportResponse(
            total=1, created=1, duplicates=0, errors=0,
            rows=[
                BulkImportRow(row=1, company_name="Gamma LLC", status="created"),
            ],
        )
        json_str = '[{"company_name": "Gamma LLC"}]'
        resp = views_client.post(
            "/companies/import",
            data={"json_data": json_str},
        )
        assert resp.status_code == 200
        mock_import.assert_called_once()
        assert "Gamma LLC" in resp.text

    def test_import_no_data_shows_error(self, views_client):
        """POST /companies/import with no file or JSON shows error."""
        resp = views_client.post(
            "/companies/import",
            data={"json_data": ""},
        )
        assert resp.status_code == 422
        assert "upload a csv" in resp.text.lower() or "paste json" in resp.text.lower()

    def test_import_invalid_json_shows_error(self, views_client):
        """POST /companies/import with invalid JSON shows error."""
        resp = views_client.post(
            "/companies/import",
            data={"json_data": "not valid json"},
        )
        assert resp.status_code == 422
        assert "Invalid JSON" in resp.text or "invalid" in resp.text.lower()


# ── Company detail tests ────────────────────────────────────────────


class TestCompanyDetail:
    @patch("app.api.views.get_company")
    def test_detail_renders(self, mock_get, views_client, mock_db_session):
        """GET /companies/1 renders company info."""
        company = _make_company_read()
        mock_get.return_value = company

        # Mock signals/analysis/briefing queries
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_order = MagicMock()
        mock_order.limit.return_value.all.return_value = []
        mock_order.first.return_value = None
        mock_filter.order_by.return_value = mock_order
        mock_query.filter.return_value = mock_filter
        mock_db_session.query.return_value = mock_query

        resp = views_client.get("/companies/1")
        assert resp.status_code == 200
        assert "Acme Corp" in resp.text
        assert "75" in resp.text  # score

    @patch("app.api.views.get_company")
    def test_detail_not_found(self, mock_get, views_client):
        """GET /companies/999 returns 404."""
        mock_get.return_value = None
        resp = views_client.get("/companies/999")
        assert resp.status_code == 404

    @patch("app.api.views.get_company")
    def test_detail_with_analysis(self, mock_get, views_client, mock_db_session):
        """Company detail shows analysis data when present."""
        company = _make_company_read()
        mock_get.return_value = company

        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.stage = "scaling_team"
        mock_analysis.stage_confidence = 80
        mock_analysis.pain_signals_json = {
            "signals": {"hiring_engineers": {"value": True}, "founder_overload": {"value": False}}
        }
        mock_analysis.evidence_bullets = ["Hiring 5 engineers", "Series A funding"]
        mock_analysis.explanation = "This company is scaling rapidly."

        def query_side_effect(model):
            mock_q = MagicMock()
            mock_f = MagicMock()
            mock_o = MagicMock()
            mock_q.filter.return_value = mock_f
            mock_f.order_by.return_value = mock_o
            if model is SignalRecord:
                mock_o.limit.return_value.all.return_value = []
            elif model is AnalysisRecord:
                mock_o.first.return_value = mock_analysis
            elif model is BriefingItem:
                mock_o.first.return_value = None
            return mock_q

        mock_db_session.query.side_effect = query_side_effect

        resp = views_client.get("/companies/1")
        assert resp.status_code == 200
        assert "scaling_team" in resp.text
        assert "80" in resp.text
        assert "Hiring Engineers" in resp.text


# ── Delete tests ────────────────────────────────────────────────────


class TestCompanyDelete:
    @patch("app.api.views.delete_company")
    def test_delete_redirects(self, mock_del, views_client):
        """POST /companies/1/delete redirects to list."""
        mock_del.return_value = True
        resp = views_client.post("/companies/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert "/companies" in resp.headers.get("location", "")

    @patch("app.api.views.delete_company")
    def test_delete_not_found(self, mock_del, views_client):
        """POST /companies/999/delete returns 404."""
        mock_del.return_value = False
        resp = views_client.post("/companies/999/delete")
        assert resp.status_code == 404


# ── Root redirect test ──────────────────────────────────────────────


class TestRootRedirect:
    def test_root_redirects_to_companies(self, views_client):
        """GET / redirects to /companies."""
        resp = views_client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/companies" in resp.headers.get("location", "")

