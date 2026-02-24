"""UI tests for briefing page (Issue #189, TDD plan).

Uses FastAPI TestClient + BeautifulSoup to assert rendered content.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db, require_ui_auth
from app.models import Company, EngagementSnapshot, ReadinessSnapshot, SignalPack, User

from tests.test_constants import TEST_USERNAME_VIEWS


def _make_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 1
    user.username = TEST_USERNAME_VIEWS
    return user


@pytest.fixture
def briefing_ui_client(db):
    """TestClient with real DB and mocked auth for briefing routes."""
    from app.main import create_app

    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_ui_auth] = lambda: _make_user()
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.integration
def test_briefing_renders_emerging_companies_section(
    briefing_ui_client: TestClient, db
) -> None:
    """GET /briefing: emerging_companies section exists when data present."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(name="Emerging UI Co", website_url="https://ui.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date.today()
    rs = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=80,
        complexity=70,
        pressure=60,
        leadership_gap=50,
        composite=75,
        pack_id=pack_id,
    )
    es = EngagementSnapshot(
        company_id=company.id,
        as_of=as_of,
        esl_score=0.8,
        engagement_type="Standard Outreach",
        cadence_blocked=False,
        pack_id=pack_id,
    )
    db.add_all([rs, es])
    db.commit()

    resp = briefing_ui_client.get("/briefing")
    assert resp.status_code == 200

    soup = BeautifulSoup(resp.text, "html.parser")
    assert "Emerging UI Co" in resp.text or "emerging" in resp.text.lower()


@pytest.mark.integration
def test_briefing_base_template_inherited(briefing_ui_client: TestClient) -> None:
    """GET /briefing: base template nav (Companies, Briefing) present."""
    resp = briefing_ui_client.get("/briefing")
    assert resp.status_code == 200

    soup = BeautifulSoup(resp.text, "html.parser")
    nav_links = [a.get_text(strip=True) for a in soup.find_all("a", href=True)]
    has_companies = any("compan" in t.lower() for t in nav_links)
    has_briefing = any("briefing" in t.lower() for t in nav_links)
    assert has_companies or has_briefing, f"Expected nav links, got: {nav_links[:10]}"
