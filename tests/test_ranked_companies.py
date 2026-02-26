"""Tests for get_ranked_companies_for_api and GET /api/companies/top (Issue #247)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Company, EngagementSnapshot, ReadinessSnapshot, SignalPack
from app.schemas.ranked_companies import RankedCompanyTop
from app.services.ranked_companies import get_ranked_companies_for_api
from tests.test_constants import TEST_USERNAME_VIEWS


@pytest.fixture(autouse=True)
def _clean_ranked_test_data(db: Session) -> None:
    """Remove readiness/engagement snapshots with future dates (handles pre-existing data)."""
    db.execute(delete(EngagementSnapshot).where(EngagementSnapshot.as_of >= date(2099, 1, 1)))
    db.execute(delete(ReadinessSnapshot).where(ReadinessSnapshot.as_of >= date(2099, 1, 1)))
    db.commit()


def _add_engagement_snapshot(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    esl_score: float = 0.8,
    engagement_type: str = "Standard Outreach",
    cadence_blocked: bool = False,
    pack_id=None,
) -> EngagementSnapshot:
    """Helper to create EngagementSnapshot for a company."""
    if pack_id is None:
        pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
        pack_id = pack.id if pack else None
    es = EngagementSnapshot(
        company_id=company_id,
        as_of=as_of,
        esl_score=esl_score,
        engagement_type=engagement_type,
        cadence_blocked=cadence_blocked,
        pack_id=pack_id,
    )
    db.add(es)
    db.commit()
    db.refresh(es)
    return es


def test_get_ranked_companies_for_api_returns_sorted_list(db: Session) -> None:
    """Returns companies ordered by composite/outreach score descending."""
    companies = [
        Company(name=f"Ranked Co {i}", website_url=f"https://ranked{i}.example.com")
        for i in range(3)
    ]
    db.add_all(companies)
    db.commit()
    for c in companies:
        db.refresh(c)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 15)
    for i, c in enumerate(companies):
        rs = ReadinessSnapshot(
            company_id=c.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=[80, 90, 70][i],
            pack_id=pack_id,
        )
        db.add(rs)
        _add_engagement_snapshot(db, c.id, as_of, esl_score=0.8)
    db.commit()

    result = get_ranked_companies_for_api(db, as_of, limit=5)

    assert len(result) == 3
    assert result[0].composite_score == 90
    assert result[1].composite_score == 80
    assert result[2].composite_score == 70
    assert result[0].company_name == "Ranked Co 1"
    assert result[0].website_url == "https://ranked1.example.com"


def test_get_ranked_companies_for_api_includes_recommendation_band(db: Session) -> None:
    """Includes recommendation_band when RS.explain has it."""
    company = Company(name="Band Co", website_url="https://band.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 16)
    rs = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=85,
        pack_id=pack_id,
        explain={"recommendation_band": "HIGH_PRIORITY"},
    )
    db.add(rs)
    _add_engagement_snapshot(db, company.id, as_of)
    db.commit()

    result = get_ranked_companies_for_api(db, as_of, limit=5)

    assert len(result) == 1
    assert result[0].recommendation_band == "HIGH_PRIORITY"


def test_get_ranked_companies_for_api_includes_top_signals(db: Session) -> None:
    """Includes top_signals from RS.explain top_events (human labels)."""
    company = Company(name="Signals Co", website_url="https://signals.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 17)
    rs = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=75,
        pack_id=pack_id,
        explain={
            "top_events": [
                {"event_type": "cto_role_posted"},
                {"event_type": "funding_raised"},
                {"event_type": "repo_activity"},
            ]
        },
    )
    db.add(rs)
    _add_engagement_snapshot(db, company.id, as_of)
    db.commit()

    result = get_ranked_companies_for_api(db, as_of, limit=5)

    assert len(result) == 1
    assert len(result[0].top_signals) == 3
    # Pack labels or formatted fallback (e.g. "Cto Role Posted", "Funding Raised", "Repo Activity")
    assert "cto" in result[0].top_signals[0].lower()
    assert "funding" in result[0].top_signals[1].lower()
    assert "repo" in result[0].top_signals[2].lower()


def test_get_ranked_companies_for_api_includes_dimension_breakdown(db: Session) -> None:
    """Includes momentum, complexity, pressure, leadership_gap from ReadinessSnapshot."""
    company = Company(name="Dims Co", website_url="https://dims.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 18)
    rs = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=72,
        complexity=65,
        pressure=58,
        leadership_gap=42,
        composite=80,
        pack_id=pack_id,
    )
    db.add(rs)
    _add_engagement_snapshot(db, company.id, as_of)
    db.commit()

    result = get_ranked_companies_for_api(db, as_of, limit=5)

    assert len(result) == 1
    assert result[0].momentum == 72
    assert result[0].complexity == 65
    assert result[0].pressure == 58
    assert result[0].leadership_gap == 42
    assert result[0].composite_score == 80


def test_get_ranked_companies_for_api_empty_db_returns_empty_list(db: Session) -> None:
    """Returns empty list when no snapshots exist for date."""
    result = get_ranked_companies_for_api(db, date(2099, 1, 19), limit=10)
    assert result == []


def test_get_ranked_companies_for_api_respects_limit(db: Session) -> None:
    """Respects limit parameter."""
    companies = [
        Company(name=f"Limit Co {i}", website_url=f"https://limit{i}.example.com")
        for i in range(5)
    ]
    db.add_all(companies)
    db.commit()
    for c in companies:
        db.refresh(c)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 20)
    # Distinct composite scores (80,75,70,65,60) -> deterministic outreach ranking
    for i, c in enumerate(companies):
        rs = ReadinessSnapshot(
            company_id=c.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=80 - (i * 5),
            pack_id=pack_id,
        )
        db.add(rs)
        _add_engagement_snapshot(db, c.id, as_of, esl_score=0.8)
    db.commit()

    result = get_ranked_companies_for_api(db, as_of, limit=2)

    assert len(result) == 2
    assert result[0].composite_score == 80
    assert result[1].composite_score == 75


def test_get_ranked_companies_for_api_respects_as_of(db: Session) -> None:
    """Returns only companies for the given as_of date."""
    company = Company(name="Date Co", website_url="https://date.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 21)
    rs = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=80,
        pack_id=pack_id,
    )
    db.add(rs)
    _add_engagement_snapshot(db, company.id, as_of)
    db.commit()

    result_same = get_ranked_companies_for_api(db, as_of, limit=5)
    result_other = get_ranked_companies_for_api(db, date(2099, 1, 22), limit=5)

    assert len(result_same) == 1
    assert len(result_other) == 0


def test_get_ranked_companies_for_api_respects_outreach_threshold(db: Session) -> None:
    """Excludes companies below outreach_score_threshold (same as get_emerging_companies)."""
    company = Company(name="Low Co", website_url="https://low.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 23)
    rs = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=50,
        complexity=50,
        pressure=50,
        leadership_gap=50,
        composite=50,
        pack_id=pack_id,
    )
    db.add(rs)
    _add_engagement_snapshot(db, company.id, as_of, esl_score=0.5)
    db.commit()

    result = get_ranked_companies_for_api(
        db, as_of, limit=5, outreach_score_threshold=30
    )
    assert len(result) == 0

    result_low = get_ranked_companies_for_api(
        db, as_of, limit=5, outreach_score_threshold=20
    )
    assert len(result_low) == 1


# ── API endpoint tests (GET /api/companies/top) ─────────────────────────────


def _make_mock_user() -> MagicMock:
    """Create a mock User for auth override."""
    user = MagicMock()
    user.id = 1
    user.username = TEST_USERNAME_VIEWS
    return user


@pytest.fixture
def api_client_with_auth(db: Session) -> TestClient:
    """TestClient with real db and auth override for /api/companies/top."""
    from app.api.deps import require_auth
    from app.db.session import get_db
    from app.main import app

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = lambda: _make_mock_user()
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(require_auth, None)


def test_api_companies_top_returns_sorted_list(api_client_with_auth: TestClient, db: Session) -> None:
    """GET /api/companies/top returns companies ordered by composite score descending."""
    companies = [
        Company(name=f"API Ranked {i}", website_url=f"https://apiranked{i}.example.com")
        for i in range(3)
    ]
    db.add_all(companies)
    db.commit()
    for c in companies:
        db.refresh(c)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 25)
    for i, c in enumerate(companies):
        rs = ReadinessSnapshot(
            company_id=c.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=[80, 90, 70][i],
            pack_id=pack_id,
        )
        db.add(rs)
        _add_engagement_snapshot(db, c.id, as_of, esl_score=0.8)
    db.commit()

    resp = api_client_with_auth.get("/api/companies/top?since=2099-01-25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["companies"]) == 3
    assert data["companies"][0]["composite_score"] == 90
    assert data["companies"][1]["composite_score"] == 80
    assert data["companies"][2]["composite_score"] == 70


def test_api_companies_top_includes_recommendation_band(api_client_with_auth: TestClient, db: Session) -> None:
    """GET /api/companies/top includes recommendation_band when available."""
    company = Company(name="API Band Co", website_url="https://apiband.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 26)
    rs = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=85,
        pack_id=pack_id,
        explain={"recommendation_band": "WATCH"},
    )
    db.add(rs)
    _add_engagement_snapshot(db, company.id, as_of)
    db.commit()

    resp = api_client_with_auth.get("/api/companies/top?since=2099-01-26")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["companies"]) == 1
    assert data["companies"][0]["recommendation_band"] == "WATCH"


def test_api_companies_top_includes_top_signals(api_client_with_auth: TestClient, db: Session) -> None:
    """GET /api/companies/top includes top_signals from pack taxonomy."""
    company = Company(name="API Signals Co", website_url="https://apisignals.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 27)
    rs = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=75,
        pack_id=pack_id,
        explain={
            "top_events": [
                {"event_type": "cto_role_posted"},
                {"event_type": "funding_raised"},
            ]
        },
    )
    db.add(rs)
    _add_engagement_snapshot(db, company.id, as_of)
    db.commit()

    resp = api_client_with_auth.get("/api/companies/top?since=2099-01-27")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["companies"]) == 1
    assert len(data["companies"][0]["top_signals"]) >= 1


def test_api_companies_top_empty_db_returns_empty_list(api_client_with_auth: TestClient) -> None:
    """GET /api/companies/top returns empty list when no snapshots for date."""
    resp = api_client_with_auth.get("/api/companies/top?since=2099-01-28")
    assert resp.status_code == 200
    data = resp.json()
    assert data["companies"] == []
    assert data["total"] == 0


def test_api_companies_top_requires_auth(client: TestClient) -> None:
    """GET /api/companies/top returns 401 without auth."""
    from app.main import app

    try:
        app.dependency_overrides.clear()
        resp = client.get("/api/companies/top")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_api_companies_top_since_limit_params(api_client_with_auth: TestClient) -> None:
    """GET /api/companies/top accepts since and limit query params."""
    from unittest.mock import patch

    with patch(
        "app.api.companies.get_ranked_companies_for_api",
        return_value=[
            RankedCompanyTop(
                company_id=1,
                company_name="Mock Co",
                website_url="https://mock.example.com",
                composite_score=80,
                recommendation_band="WATCH",
                top_signals=[],
            )
        ],
    ):
        resp = api_client_with_auth.get("/api/companies/top?since=2026-02-15&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["companies"][0]["company_name"] == "Mock Co"
