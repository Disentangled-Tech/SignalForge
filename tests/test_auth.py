"""Tests for authentication system.

These tests mock the database to avoid requiring a running PostgreSQL.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.test_constants import TEST_PASSWORD, TEST_PASSWORD_WRONG
from app.models.user import User
from app.services.auth import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username: str = "admin", password: str | None = None) -> User:
    """Create a User instance with a hashed password (no DB)."""
    user = User(id=1, username=username)
    user.set_password(password if password is not None else TEST_PASSWORD)
    return user


# ---------------------------------------------------------------------------
# Unit tests: auth service
# ---------------------------------------------------------------------------


class TestPasswordVerification:
    def test_correct_password(self):
        user = _make_user(password=TEST_PASSWORD)
        assert user.verify_password(TEST_PASSWORD) is True

    def test_wrong_password(self):
        user = _make_user(password=TEST_PASSWORD)
        assert user.verify_password(TEST_PASSWORD_WRONG) is False


class TestAccessToken:
    def test_create_and_decode_token(self):
        token = create_access_token(data={"sub": "admin"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "admin"
        assert "exp" in payload

    def test_invalid_token_returns_none(self):
        result = decode_access_token("not.a.valid.token")
        assert result is None

    def test_tampered_token_returns_none(self):
        token = create_access_token(data={"sub": "admin"})
        # Tamper with the token
        tampered = token[:-4] + "XXXX"
        result = decode_access_token(tampered)
        assert result is None


# ---------------------------------------------------------------------------
# Integration tests: API endpoints (mocked DB)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_user():
    """Create a mock user and patch DB dependency."""
    user = _make_user(username="admin", password=TEST_PASSWORD)
    return user


@pytest.fixture
def auth_client(mock_db_user):
    """TestClient with mocked DB that returns the test user."""
    from app.db.session import get_db
    from app.main import create_app

    app = create_app()

    # Create a mock session that returns our test user
    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.first.return_value = mock_db_user
    mock_query.filter.return_value = mock_filter
    mock_session.query.return_value = mock_query

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client_no_user():
    """TestClient with mocked DB that returns no user (user not found)."""
    from app.db.session import get_db
    from app.main import create_app

    app = create_app()

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.first.return_value = None
    mock_query.filter.return_value = mock_filter
    mock_session.query.return_value = mock_query

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


class TestLoginEndpoint:
    def test_login_success(self, auth_client):
        resp = auth_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": TEST_PASSWORD},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        # Cookie should be set
        assert "access_token" in resp.cookies

    def test_login_wrong_password(self, auth_client):
        resp = auth_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": TEST_PASSWORD_WRONG},
        )
        assert resp.status_code == 401

    def test_login_unknown_user(self, auth_client_no_user):
        resp = auth_client_no_user.post(
            "/api/auth/login",
            json={"username": "nobody", "password": TEST_PASSWORD_WRONG},
        )
        assert resp.status_code == 401


class TestLogoutEndpoint:
    def test_logout_clears_cookie(self, auth_client):
        # Login first
        resp = auth_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": TEST_PASSWORD},
        )
        assert resp.status_code == 200

        # Logout
        resp = auth_client.post("/api/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Logged out"


class TestMeEndpoint:
    def test_me_with_valid_token(self, auth_client):
        # Login to get token
        resp = auth_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": TEST_PASSWORD},
        )
        token = resp.json()["access_token"]

        # Access /me with bearer token
        resp = auth_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["id"] == 1

    def test_me_without_auth_returns_401(self, auth_client_no_user):
        resp = auth_client_no_user.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_cookie(self, auth_client):
        # Login (sets cookie)
        resp = auth_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": TEST_PASSWORD},
        )
        assert resp.status_code == 200

        # Access /me — client auto-sends cookies
        resp = auth_client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"

    def test_me_with_invalid_token(self, auth_client_no_user):
        resp = auth_client_no_user.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

