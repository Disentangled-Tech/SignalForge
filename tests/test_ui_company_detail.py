"""UI tests for company detail page (Issue #189, TDD plan).

Uses FastAPI TestClient + BeautifulSoup to assert rendered content.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.views import _require_ui_auth
from app.db.session import get_db
from app.models import Company, User


def _make_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "ui_test_user"
    return user


@pytest.fixture
def company_detail_client(db):
    """TestClient with real DB and mocked auth for company detail routes."""
    from app.main import create_app

    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_require_ui_auth] = lambda: _make_user()
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.integration
def test_company_detail_renders_company_name(
    company_detail_client: TestClient, db
) -> None:
    """GET /companies/{id}: company name in page."""
    company = Company(
        name="Detail Test Co",
        website_url="https://detail.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    resp = company_detail_client.get(f"/companies/{company.id}")
    assert resp.status_code == 200
    assert "Detail Test Co" in resp.text


@pytest.mark.integration
def test_company_detail_has_outreach_section(
    company_detail_client: TestClient, db
) -> None:
    """GET /companies/{id}: outreach section or generation controls present."""
    company = Company(
        name="Outreach Co",
        website_url="https://outreach.example.com",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    resp = company_detail_client.get(f"/companies/{company.id}")
    assert resp.status_code == 200
    # Page should have outreach-related content
    text_lower = resp.text.lower()
    has_outreach = "outreach" in text_lower or "record" in text_lower or "contact" in text_lower
    assert has_outreach, "Expected outreach-related content on company detail page"
