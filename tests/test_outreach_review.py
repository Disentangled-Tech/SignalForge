"""Tests for weekly outreach review endpoint (Issue #108)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Company, EngagementSnapshot, OutreachHistory, ReadinessSnapshot
from app.services.outreach_review import (
    get_latest_snapshot_date,
    get_weekly_review_companies,
)


# Use unique date to avoid collision with other tests
_REVIEW_AS_OF = date(2099, 2, 1)


@pytest.fixture(autouse=True)
def _clean_review_test_data(db: Session) -> None:
    """Remove test data to avoid pollution."""
    db.execute(delete(OutreachHistory))
    db.execute(delete(EngagementSnapshot).where(EngagementSnapshot.as_of == _REVIEW_AS_OF))
    db.execute(delete(ReadinessSnapshot).where(ReadinessSnapshot.as_of == _REVIEW_AS_OF))
    db.commit()


def _add_snapshots(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    composite: int = 80,
    esl_score: float = 0.8,
    outreach_score: int | None = None,
) -> None:
    """Create ReadinessSnapshot + EngagementSnapshot for a company."""
    rs = ReadinessSnapshot(
        company_id=company_id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=composite,
    )
    db.add(rs)
    es = EngagementSnapshot(
        company_id=company_id,
        as_of=as_of,
        esl_score=esl_score,
        engagement_type="Standard Outreach",
        outreach_score=outreach_score or round(composite * esl_score),
    )
    db.add(es)
    db.commit()


@pytest.fixture
def api_client(db: Session) -> TestClient:
    """TestClient with real DB and mocked auth."""
    from app.main import app
    from app.api.deps import require_auth
    from app.db.session import get_db

    def override_get_db():
        yield db

    def override_auth():
        pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = override_auth
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestGetWeeklyReviewCompanies:
    """Service-level tests."""

    def test_returns_top_by_outreach_score(self, db: Session) -> None:
        """Sorted by OutreachScore DESC, limit enforced."""
        companies = [
            Company(name=f"Review Co {i}", website_url=f"https://review{i}.example.com")
            for i in range(5)
        ]
        db.add_all(companies)
        db.commit()
        for c in companies:
            db.refresh(c)

        composites = [70, 80, 90, 60, 65]
        esls = [0.5, 0.8, 0.6, 1.0, 0.9]
        for i, c in enumerate(companies):
            _add_snapshots(db, c.id, _REVIEW_AS_OF, composite=composites[i], esl_score=esls[i])
        db.commit()

        result = get_weekly_review_companies(
            db, _REVIEW_AS_OF, limit=3, outreach_score_threshold=30
        )

        assert len(result) == 3
        scores = [r["outreach_score"] for r in result]
        assert scores == [64, 60, 58]  # descending

    def test_excludes_cooldown_companies(self, db: Session) -> None:
        """Company with last outreach 10 days ago not in result."""
        company = Company(name="Cooldown Co", website_url="https://cooldown.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        _add_snapshots(db, company.id, _REVIEW_AS_OF, composite=80, esl_score=0.9)
        as_of_dt = datetime.combine(_REVIEW_AS_OF, datetime.min.time()).replace(tzinfo=timezone.utc)
        ten_days_ago = as_of_dt - timedelta(days=10)
        oh = OutreachHistory(
            company_id=company.id,
            outreach_type="email",
            sent_at=ten_days_ago,
        )
        db.add(oh)
        db.commit()

        result = get_weekly_review_companies(
            db, _REVIEW_AS_OF, limit=10, outreach_score_threshold=30
        )

        assert len(result) == 0

    def test_excludes_declined_companies(self, db: Session) -> None:
        """Company with declined outcome in 180 days not in result."""
        company = Company(name="Declined Co", website_url="https://declined.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        _add_snapshots(db, company.id, _REVIEW_AS_OF, composite=80, esl_score=0.9)
        as_of_dt = datetime.combine(_REVIEW_AS_OF, datetime.min.time()).replace(tzinfo=timezone.utc)
        hundred_days_ago = as_of_dt - timedelta(days=100)
        oh = OutreachHistory(
            company_id=company.id,
            outreach_type="email",
            sent_at=hundred_days_ago,
            outcome="declined",
        )
        db.add(oh)
        db.commit()

        result = get_weekly_review_companies(
            db, _REVIEW_AS_OF, limit=10, outreach_score_threshold=30
        )

        assert len(result) == 0

    def test_includes_companies_past_cooldown(self, db: Session) -> None:
        """Company with last outreach 61 days ago included."""
        company = Company(name="Allowed Co", website_url="https://allowed.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        _add_snapshots(db, company.id, _REVIEW_AS_OF, composite=80, esl_score=0.9)
        as_of_dt = datetime.combine(_REVIEW_AS_OF, datetime.min.time()).replace(tzinfo=timezone.utc)
        sixty_one_days_ago = as_of_dt - timedelta(days=61)
        oh = OutreachHistory(
            company_id=company.id,
            outreach_type="email",
            sent_at=sixty_one_days_ago,
        )
        db.add(oh)
        db.commit()

        result = get_weekly_review_companies(
            db, _REVIEW_AS_OF, limit=10, outreach_score_threshold=30
        )

        assert len(result) == 1
        assert result[0]["company_id"] == company.id
        assert result[0]["outreach_score"] == 72  # round(80 * 0.9)

    def test_respects_weekly_limit(self, db: Session) -> None:
        """Returns at most limit companies."""
        companies = [
            Company(name=f"Limit Co {i}", website_url=f"https://limit{i}.example.com")
            for i in range(5)
        ]
        db.add_all(companies)
        db.commit()
        for c in companies:
            db.refresh(c)

        for i, c in enumerate(companies):
            _add_snapshots(db, c.id, _REVIEW_AS_OF, composite=70 + i * 5, esl_score=0.8)
        db.commit()

        result = get_weekly_review_companies(
            db, _REVIEW_AS_OF, limit=2, outreach_score_threshold=30
        )

        assert len(result) == 2

    def test_includes_explain_block(self, db: Session) -> None:
        """Each item has explain with expected structure."""
        company = Company(name="Explain Co", website_url="https://explain.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        _add_snapshots(db, company.id, _REVIEW_AS_OF, composite=80, esl_score=0.8)
        db.commit()

        result = get_weekly_review_companies(
            db, _REVIEW_AS_OF, limit=10, outreach_score_threshold=30
        )

        assert len(result) == 1
        assert "explain" in result[0]
        assert isinstance(result[0]["explain"], dict)

    def test_no_duplicate_companies(self, db: Session) -> None:
        """Each company_id appears once."""
        companies = [
            Company(name=f"Dedup Co {i}", website_url=f"https://dedup{i}.example.com")
            for i in range(3)
        ]
        db.add_all(companies)
        db.commit()
        for c in companies:
            db.refresh(c)

        for i, c in enumerate(companies):
            _add_snapshots(db, c.id, _REVIEW_AS_OF, composite=70 + i * 10, esl_score=0.8)
        db.commit()

        result = get_weekly_review_companies(
            db, _REVIEW_AS_OF, limit=10, outreach_score_threshold=30
        )

        ids = [r["company_id"] for r in result]
        assert len(ids) == len(set(ids))

    def test_empty_when_no_snapshots(self, db: Session) -> None:
        """Returns empty list when no engagement snapshots for date."""
        result = get_weekly_review_companies(
            db, _REVIEW_AS_OF, limit=10, outreach_score_threshold=30
        )
        assert result == []


class TestGetLatestSnapshotDate:
    """Tests for get_latest_snapshot_date."""

    def test_returns_latest_when_exists(self, db: Session) -> None:
        """Returns most recent as_of when snapshots exist."""
        company = Company(name="Latest Co", website_url="https://latest.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)
        _add_snapshots(db, company.id, _REVIEW_AS_OF)
        db.commit()

        latest = get_latest_snapshot_date(db)
        assert latest is not None
        assert latest >= _REVIEW_AS_OF



class TestOutreachReviewAPI:
    """API endpoint tests."""

    def test_review_returns_200_with_data(
        self, db: Session, api_client: TestClient
    ) -> None:
        """GET /api/outreach/review returns 200 and expected structure."""
        company = Company(name="API Co", website_url="https://api.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)
        _add_snapshots(db, company.id, _REVIEW_AS_OF, composite=80, esl_score=0.8)
        db.commit()

        resp = api_client.get(f"/api/outreach/review?date={_REVIEW_AS_OF.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        assert "as_of" in data
        assert "companies" in data
        assert data["as_of"] == _REVIEW_AS_OF.isoformat()
        assert len(data["companies"]) >= 1
        item = data["companies"][0]
        assert "company_id" in item
        assert "company_name" in item
        assert "outreach_score" in item
        assert "explain" in item

    def test_review_requires_auth(self, client: TestClient) -> None:
        """GET /api/outreach/review without auth returns 401."""
        resp = client.get("/api/outreach/review")
        assert resp.status_code == 401
