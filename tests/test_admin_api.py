"""Tests for admin API — pack metadata (Issue #172, Phase 3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, require_auth
from app.main import app
from tests.test_constants import TEST_USERNAME_VIEWS


def _make_user():
    from app.models.user import User

    user = MagicMock(spec=User)
    user.id = 1
    user.username = TEST_USERNAME_VIEWS
    return user


@pytest.fixture
def admin_client(db):
    """TestClient with auth override for admin API tests."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = lambda: _make_user()
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestAdminPacks:
    """GET /api/admin/packs lists installed packs with metadata."""

    def test_admin_packs_returns_200_with_packs_list(self, admin_client: TestClient) -> None:
        """GET /api/admin/packs returns 200 and packs array."""
        resp = admin_client.get("/api/admin/packs")
        assert resp.status_code == 200
        data = resp.json()
        assert "packs" in data
        assert isinstance(data["packs"], list)

    def test_admin_packs_includes_metadata(self, admin_client: TestClient, db) -> None:
        """Each pack has pack_id, version, name, schema_version, active."""
        resp = admin_client.get("/api/admin/packs")
        assert resp.status_code == 200
        data = resp.json()
        packs = data["packs"]
        if packs:
            p = packs[0]
            assert "pack_id" in p
            assert "version" in p
            assert "name" in p
            assert "schema_version" in p
            assert "active" in p

    def test_admin_packs_requires_auth(self, db) -> None:
        """GET /api/admin/packs returns 401 without auth."""
        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        # Do NOT override require_auth
        client = TestClient(app)
        try:
            resp = client.get("/api/admin/packs")
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()
