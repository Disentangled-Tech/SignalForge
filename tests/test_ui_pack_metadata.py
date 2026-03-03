"""UI tests for pack metadata display (Issue #172).

Tests that settings page shows active pack metadata when implemented.
These tests FAIL until pack metadata is rendered in /settings (Phase 3).
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from app.api.deps import get_db, require_ui_auth
from app.main import app
from tests.test_constants import TEST_USERNAME_VIEWS


def _make_user():
    from unittest.mock import MagicMock

    from app.models.user import User

    user = MagicMock(spec=User)
    user.id = 1
    user.username = TEST_USERNAME_VIEWS
    return user


@pytest.fixture
def pack_ui_client(db):
    """TestClient with auth override for pack metadata UI tests."""

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_ui_auth] = lambda: _make_user()
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestSettingsPackMetadata:
    """GET /settings shows active pack metadata (Issue #172 acceptance criteria).

    Fails until: settings template includes active_pack with pack_id, version, name.
    """

    def test_settings_shows_active_pack_section(self, pack_ui_client: TestClient) -> None:
        """Settings page has section showing active pack (Fractional CTO v1)."""
        resp = pack_ui_client.get("/settings")
        assert resp.status_code == 200
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        assert (
            "fractional_cto" in text.lower()
            or "active pack" in text.lower()
            or "signal pack" in text.lower()
        ), (
            "Settings must show active pack metadata (Issue #172). "
            "Expected 'fractional_cto' or 'Active pack' or 'Signal pack' in page."
        )

    def test_settings_pack_section_includes_version(self, pack_ui_client: TestClient) -> None:
        """When pack section exists, it shows version (e.g. fractional_cto_v1 or 'version 1')."""
        resp = pack_ui_client.get("/settings")
        assert resp.status_code == 200
        text = resp.text.lower()
        if "fractional_cto" in text or "active pack" in text:
            assert "v1" in text or "version 1" in text or "fractional_cto_v1" in text, (
                "Pack version must be visible (Issue #172)."
            )

    def test_settings_pack_section_no_auto_reprocess_messaging(
        self, pack_ui_client: TestClient
    ) -> None:
        """When pack section exists, no-auto-reprocess messaging present (ADR-003)."""
        resp = pack_ui_client.get("/settings")
        assert resp.status_code == 200
        text = resp.text.lower()
        if "fractional_cto" in text or "active pack" in text:
            assert any(
                phrase in text
                for phrase in ["reprocess", "new observations", "going forward", "apply only"]
            ), "Pack section must include no-auto-reprocess messaging per ADR-003."
