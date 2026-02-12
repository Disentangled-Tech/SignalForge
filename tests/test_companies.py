"""Tests for Company CRUD API and service layer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.company import Company
from app.schemas.company import (
    BulkImportResponse,
    CompanyCreate,
    CompanyRead,
    CompanySource,
    CompanyUpdate,
)
from app.services.company import (
    _model_to_read,
    _schema_to_model_data,
    bulk_import_companies,
    create_company,
    delete_company,
    get_company,
    list_companies,
    update_company,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _make_company(**overrides) -> MagicMock:
    """Create a mock Company model instance with sensible defaults."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, name="Acme Corp", website_url="https://acme.example.com",
        founder_name="Jane Doe", founder_linkedin_url=None,
        company_linkedin_url=None, source="manual",
        target_profile_match=False, current_stage=None, notes=None,
        cto_need_score=None, created_at=now, updated_at=now, last_scan_at=None,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=Company)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ── Field mapping tests ─────────────────────────────────────────────


class TestFieldMapping:
    def test_schema_to_model_maps_company_name(self) -> None:
        data = CompanyCreate(company_name="Test Co")
        result = _schema_to_model_data(data)
        assert "name" in result
        assert result["name"] == "Test Co"
        assert "company_name" not in result

    def test_schema_to_model_maps_target_profile_match_truthy(self) -> None:
        data = CompanyCreate(company_name="X", target_profile_match="Yes")
        result = _schema_to_model_data(data)
        assert result["target_profile_match"] is True

    def test_schema_to_model_maps_target_profile_match_none(self) -> None:
        data = CompanyCreate(company_name="X")
        result = _schema_to_model_data(data)
        assert result["target_profile_match"] is False

    def test_schema_to_model_maps_source_enum(self) -> None:
        data = CompanyCreate(company_name="X", source=CompanySource.referral)
        result = _schema_to_model_data(data)
        assert result["source"] == "referral"

    def test_update_exclude_unset(self) -> None:
        data = CompanyUpdate(company_name="New Name")
        result = _schema_to_model_data(data, is_update=True)
        assert result == {"name": "New Name"}

    def test_model_to_read_maps_name_to_company_name(self) -> None:
        company = _make_company(name="Mapped Co", target_profile_match=True)
        read = _model_to_read(company)
        assert read.company_name == "Mapped Co"
        assert read.target_profile_match == "True"

    def test_model_to_read_target_false_is_none(self) -> None:
        company = _make_company(target_profile_match=False)
        read = _model_to_read(company)
        assert read.target_profile_match is None


# ── Service layer tests ─────────────────────────────────────────────


class TestServiceCRUD:
    def _mock_db(self):
        return MagicMock()

    def test_get_company_found(self) -> None:
        db = self._mock_db()
        company = _make_company()
        db.query.return_value.filter.return_value.first.return_value = company
        result = get_company(db, 1)
        assert result is not None
        assert result.company_name == "Acme Corp"

    def test_get_company_not_found(self) -> None:
        db = self._mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        result = get_company(db, 999)
        assert result is None

    def test_create_company(self) -> None:
        db = self._mock_db()
        now = datetime.now(timezone.utc)

        def fake_refresh(obj):
            # Simulate DB setting defaults after commit
            if not hasattr(obj, "id") or obj.id is None:
                object.__setattr__(obj, "id", 1)
            if not hasattr(obj, "created_at") or obj.created_at is None:
                object.__setattr__(obj, "created_at", now)
            if not hasattr(obj, "updated_at") or obj.updated_at is None:
                object.__setattr__(obj, "updated_at", now)

        db.refresh = MagicMock(side_effect=fake_refresh)
        data = CompanyCreate(company_name="New Co")
        result = create_company(db, data)
        assert result.company_name == "New Co"
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_update_company_found(self) -> None:
        db = self._mock_db()
        company = _make_company(name="Old Name")
        db.query.return_value.filter.return_value.first.return_value = company
        db.refresh = MagicMock(side_effect=lambda x: None)

        data = CompanyUpdate(company_name="Updated Name")
        result = update_company(db, 1, data)
        assert result is not None
        assert company.name == "Updated Name"
        db.commit.assert_called_once()

    def test_update_company_not_found(self) -> None:
        db = self._mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        result = update_company(db, 999, CompanyUpdate(company_name="X"))
        assert result is None

    def test_delete_company_found(self) -> None:
        db = self._mock_db()
        company = _make_company()
        db.query.return_value.filter.return_value.first.return_value = company
        result = delete_company(db, 1)
        assert result is True
        db.delete.assert_called_once_with(company)
        db.commit.assert_called_once()

    def test_delete_company_not_found(self) -> None:
        db = self._mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        result = delete_company(db, 999)
        assert result is False

    def test_list_companies_basic(self) -> None:
        db = self._mock_db()
        company = _make_company()
        query_mock = db.query.return_value
        query_mock.count.return_value = 1
        query_mock.order_by.return_value = query_mock
        query_mock.offset.return_value = query_mock
        query_mock.limit.return_value.all.return_value = [company]
        items, total = list_companies(db)
        assert total == 1
        assert len(items) == 1
        assert items[0].company_name == "Acme Corp"

    def test_list_companies_with_search(self) -> None:
        db = self._mock_db()
        query_mock = db.query.return_value
        filter_mock = query_mock.filter.return_value
        filter_mock.count.return_value = 0
        filter_mock.order_by.return_value = filter_mock
        filter_mock.offset.return_value = filter_mock
        filter_mock.limit.return_value.all.return_value = []
        items, total = list_companies(db, search="nonexistent")
        assert total == 0
        assert len(items) == 0


# ── API endpoint tests ──────────────────────────────────────────────


class TestCompanyAPI:
    """Tests for the company REST endpoints using FastAPI TestClient."""

    @pytest.fixture
    def api_client(self) -> TestClient:
        """TestClient with mocked DB and auth dependencies."""
        from app.main import app
        from app.db.session import get_db
        from app.api.deps import require_auth

        self._mock_db = MagicMock()

        def override_get_db():
            yield self._mock_db

        async def override_auth():
            pass

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_auth] = override_auth
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    def test_create_company_api(self, api_client: TestClient) -> None:
        now = datetime.now(timezone.utc)
        company = _make_company(name="API Co")

        def fake_refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                object.__setattr__(obj, "id", 1)
            if not hasattr(obj, "created_at") or obj.created_at is None:
                object.__setattr__(obj, "created_at", now)
            if not hasattr(obj, "updated_at") or obj.updated_at is None:
                object.__setattr__(obj, "updated_at", now)

        self._mock_db.refresh = MagicMock(side_effect=fake_refresh)

        response = api_client.post(
            "/api/companies",
            json={"company_name": "API Co"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["company_name"] == "API Co"

    def test_create_company_validation_error(self, api_client: TestClient) -> None:
        response = api_client.post("/api/companies", json={})
        assert response.status_code == 422

    def test_get_company_not_found(self, api_client: TestClient) -> None:
        self._mock_db.query.return_value.filter.return_value.first.return_value = None
        response = api_client.get("/api/companies/999")
        assert response.status_code == 404

    def test_get_company_found(self, api_client: TestClient) -> None:
        company = _make_company()
        self._mock_db.query.return_value.filter.return_value.first.return_value = company
        response = api_client.get("/api/companies/1")
        assert response.status_code == 200
        data = response.json()
        assert data["company_name"] == "Acme Corp"
        assert data["id"] == 1

    def test_list_companies_api(self, api_client: TestClient) -> None:
        company = _make_company()
        query_mock = self._mock_db.query.return_value
        query_mock.count.return_value = 1
        query_mock.order_by.return_value = query_mock
        query_mock.offset.return_value = query_mock
        query_mock.limit.return_value.all.return_value = [company]
        response = api_client.get("/api/companies")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_list_companies_pagination(self, api_client: TestClient) -> None:
        query_mock = self._mock_db.query.return_value
        query_mock.count.return_value = 50
        query_mock.order_by.return_value = query_mock
        query_mock.offset.return_value = query_mock
        query_mock.limit.return_value.all.return_value = []
        response = api_client.get("/api/companies?page=3&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 3
        assert data["page_size"] == 10

    def test_list_companies_invalid_sort(self, api_client: TestClient) -> None:
        response = api_client.get("/api/companies?sort_by=invalid")
        assert response.status_code == 422

    def test_update_company_api(self, api_client: TestClient) -> None:
        company = _make_company()
        self._mock_db.query.return_value.filter.return_value.first.return_value = company
        self._mock_db.refresh = MagicMock(side_effect=lambda x: None)
        response = api_client.put(
            "/api/companies/1",
            json={"company_name": "Updated Co"},
        )
        assert response.status_code == 200
        assert company.name == "Updated Co"

    def test_update_company_not_found(self, api_client: TestClient) -> None:
        self._mock_db.query.return_value.filter.return_value.first.return_value = None
        response = api_client.put(
            "/api/companies/999",
            json={"company_name": "Nope"},
        )
        assert response.status_code == 404

    def test_delete_company_api(self, api_client: TestClient) -> None:
        company = _make_company()
        self._mock_db.query.return_value.filter.return_value.first.return_value = company
        response = api_client.delete("/api/companies/1")
        assert response.status_code == 204

    def test_delete_company_not_found(self, api_client: TestClient) -> None:
        self._mock_db.query.return_value.filter.return_value.first.return_value = None
        response = api_client.delete("/api/companies/999")
        assert response.status_code == 404



# ── Bulk import service tests ────────────────────────────────────────


class TestBulkImportService:
    def _mock_db(self):
        return MagicMock()

    def test_import_creates_new_companies(self) -> None:
        db = self._mock_db()
        now = datetime.now(timezone.utc)
        # No duplicates found
        db.query.return_value.filter.return_value.first.return_value = None

        def fake_refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                object.__setattr__(obj, "id", 1)
            if not hasattr(obj, "created_at") or obj.created_at is None:
                object.__setattr__(obj, "created_at", now)
            if not hasattr(obj, "updated_at") or obj.updated_at is None:
                object.__setattr__(obj, "updated_at", now)

        db.refresh = MagicMock(side_effect=fake_refresh)

        companies = [
            CompanyCreate(company_name="Alpha Inc"),
            CompanyCreate(company_name="Beta Corp"),
        ]
        result = bulk_import_companies(db, companies)
        assert result.total == 2
        assert result.created == 2
        assert result.duplicates == 0
        assert result.errors == 0
        assert len(result.rows) == 2
        assert result.rows[0].status == "created"
        assert result.rows[1].status == "created"

    def test_import_detects_duplicates(self) -> None:
        db = self._mock_db()
        existing = _make_company(id=42, name="Existing Co")
        db.query.return_value.filter.return_value.first.return_value = existing

        companies = [CompanyCreate(company_name="Existing Co")]
        result = bulk_import_companies(db, companies)
        assert result.total == 1
        assert result.created == 0
        assert result.duplicates == 1
        assert result.rows[0].status == "duplicate"

    def test_import_empty_list(self) -> None:
        db = self._mock_db()
        result = bulk_import_companies(db, [])
        assert result.total == 0
        assert result.created == 0
        assert result.duplicates == 0
        assert result.errors == 0
        assert result.rows == []

    def test_import_mixed_results(self) -> None:
        db = self._mock_db()
        now = datetime.now(timezone.utc)
        existing = _make_company(id=10, name="Dupe Co")

        call_count = 0

        def filter_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_filter = MagicMock()
            # First call: no duplicate (new company), Second call: duplicate found
            if call_count == 1:
                mock_filter.first.return_value = None
            else:
                mock_filter.first.return_value = existing
            return mock_filter

        db.query.return_value.filter = MagicMock(side_effect=filter_side_effect)

        def fake_refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                object.__setattr__(obj, "id", 1)
            if not hasattr(obj, "created_at") or obj.created_at is None:
                object.__setattr__(obj, "created_at", now)
            if not hasattr(obj, "updated_at") or obj.updated_at is None:
                object.__setattr__(obj, "updated_at", now)

        db.refresh = MagicMock(side_effect=fake_refresh)

        companies = [
            CompanyCreate(company_name="New Co"),
            CompanyCreate(company_name="Dupe Co"),
        ]
        result = bulk_import_companies(db, companies)
        assert result.total == 2
        assert result.created == 1
        assert result.duplicates == 1


# ── Bulk import API tests ────────────────────────────────────────────


class TestBulkImportAPI:
    """Tests for the POST /api/companies/import endpoint."""

    @pytest.fixture
    def api_client(self) -> TestClient:
        """TestClient with mocked DB and auth dependencies."""
        from app.main import app
        from app.db.session import get_db
        from app.api.deps import require_auth

        self._mock_db = MagicMock()

        def override_get_db():
            yield self._mock_db

        async def override_auth():
            pass

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_auth] = override_auth
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    @pytest.fixture
    def unauth_client(self) -> TestClient:
        """TestClient without auth override (requires real auth)."""
        from app.main import app

        app.dependency_overrides.clear()
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    def _setup_no_duplicates(self):
        """Configure mock DB to find no duplicates and handle refresh."""
        now = datetime.now(timezone.utc)
        self._mock_db.query.return_value.filter.return_value.first.return_value = None

        def fake_refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                object.__setattr__(obj, "id", 1)
            if not hasattr(obj, "created_at") or obj.created_at is None:
                object.__setattr__(obj, "created_at", now)
            if not hasattr(obj, "updated_at") or obj.updated_at is None:
                object.__setattr__(obj, "updated_at", now)

        self._mock_db.refresh = MagicMock(side_effect=fake_refresh)

    def test_json_import_happy_path(self, api_client: TestClient) -> None:
        self._setup_no_duplicates()
        response = api_client.post(
            "/api/companies/import",
            json={
                "companies": [
                    {"company_name": "Alpha Inc"},
                    {"company_name": "Beta Corp", "website_url": "https://beta.example.com"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["created"] == 2
        assert data["duplicates"] == 0
        assert data["errors"] == 0
        assert len(data["rows"]) == 2

    def test_csv_import_happy_path(self, api_client: TestClient) -> None:
        self._setup_no_duplicates()
        csv_content = "company_name,website_url\nAlpha Inc,https://alpha.example.com\nBeta Corp,\n"
        response = api_client.post(
            "/api/companies/import",
            files={"file": ("companies.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["created"] == 2
        assert data["duplicates"] == 0
        assert data["errors"] == 0

    def test_json_import_duplicate_detection(self, api_client: TestClient) -> None:
        existing = _make_company(id=42, name="Existing Co")
        self._mock_db.query.return_value.filter.return_value.first.return_value = existing
        response = api_client.post(
            "/api/companies/import",
            json={"companies": [{"company_name": "Existing Co"}]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["created"] == 0
        assert data["duplicates"] == 1
        assert data["rows"][0]["status"] == "duplicate"

    def test_csv_import_missing_company_name(self, api_client: TestClient) -> None:
        self._setup_no_duplicates()
        csv_content = "company_name,website_url\n,https://noname.example.com\nGood Co,\n"
        response = api_client.post(
            "/api/companies/import",
            files={"file": ("companies.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["errors"] == 1
        assert data["created"] == 1
        # Find the error row
        error_rows = [r for r in data["rows"] if r["status"] == "error"]
        assert len(error_rows) == 1
        assert "Missing company_name" in error_rows[0]["detail"]

    def test_json_import_empty_list(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/api/companies/import",
            json={"companies": []},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["created"] == 0
        assert data["rows"] == []

    def test_import_requires_auth(self, unauth_client: TestClient) -> None:
        response = unauth_client.post(
            "/api/companies/import",
            json={"companies": [{"company_name": "Test"}]},
        )
        assert response.status_code == 401