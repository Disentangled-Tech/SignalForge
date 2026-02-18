"""Watchlist API endpoint tests (Issue #94)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Company, ReadinessSnapshot, Watchlist


@pytest.fixture
def api_client(db: Session):
    """TestClient with real DB and mocked auth."""
    from app.main import app
    from app.db.session import get_db
    from app.api.deps import require_auth

    def override_get_db():
        yield db

    async def override_auth():
        pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = override_auth
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()




class TestWatchlistAdd:
    """Tests for POST /api/watchlist."""

    def test_add_to_watchlist_success(self, db: Session, api_client: TestClient) -> None:
        """POST with valid company_id returns 201 and creates entry."""
        company = Company(name="WatchlistCo", website_url="https://watch.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        response = api_client.post(
            "/api/watchlist",
            json={"company_id": company.id, "reason": "High readiness"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["company_id"] == company.id
        assert "added_at" in data

        entry = db.query(Watchlist).filter(Watchlist.company_id == company.id).first()
        assert entry is not None
        assert entry.is_active is True
        assert entry.added_reason == "High readiness"

    def test_add_to_watchlist_duplicate_returns_409(
        self, db: Session, api_client: TestClient
    ) -> None:
        """POST same company twice — second returns 409."""
        company = Company(name="DupWatchCo", website_url="https://dupwatch.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        r1 = api_client.post("/api/watchlist", json={"company_id": company.id})
        assert r1.status_code == 201

        r2 = api_client.post("/api/watchlist", json={"company_id": company.id})
        assert r2.status_code == 409
        assert "already on the watchlist" in r2.json()["detail"]

    def test_add_to_watchlist_company_not_found_404(
        self, api_client: TestClient
    ) -> None:
        """POST non-existent company_id returns 404."""
        response = api_client.post(
            "/api/watchlist",
            json={"company_id": 99999, "reason": "N/A"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestWatchlistRemove:
    """Tests for DELETE /api/watchlist/{company_id}."""

    def test_remove_from_watchlist_success(
        self, db: Session, api_client: TestClient
    ) -> None:
        """DELETE existing entry returns 204 and sets is_active=False."""
        company = Company(name="RemoveCo", website_url="https://remove.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)
        entry = Watchlist(company_id=company.id, is_active=True)
        db.add(entry)
        db.commit()

        response = api_client.delete(f"/api/watchlist/{company.id}")
        assert response.status_code == 204

        db.refresh(entry)
        assert entry.is_active is False

    def test_remove_from_watchlist_not_found_404(
        self, db: Session, api_client: TestClient
    ) -> None:
        """DELETE company not on watchlist returns 404."""
        company = Company(name="NotWatchedCo", website_url="https://nw.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        response = api_client.delete(f"/api/watchlist/{company.id}")
        assert response.status_code == 404
        assert "not on watchlist" in response.json()["detail"]


class TestWatchlistList:
    """Tests for GET /api/watchlist."""

    def test_list_watchlist_empty(self, db: Session, api_client: TestClient) -> None:
        """GET when empty returns 200 with items=[]."""
        # Isolate: deactivate all watchlist entries so list is empty
        db.query(Watchlist).filter(Watchlist.is_active == True).update(
            {"is_active": False}
        )
        db.commit()

        response = api_client.get("/api/watchlist")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

    def test_list_watchlist_with_composite_and_delta(
        self, db: Session, api_client: TestClient
    ) -> None:
        """GET returns items with latest_composite and delta_7d."""
        company = Company(name="DeltaCo", website_url="https://delta.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        entry = Watchlist(company_id=company.id, added_reason="Test", is_active=True)
        db.add(entry)
        db.commit()

        today = date.today()
        prev_date = today - timedelta(days=7)

        snap_today = ReadinessSnapshot(
            company_id=company.id,
            as_of=today,
            momentum=70,
            complexity=65,
            pressure=60,
            leadership_gap=55,
            composite=72,
        )
        snap_prev = ReadinessSnapshot(
            company_id=company.id,
            as_of=prev_date,
            momentum=60,
            complexity=60,
            pressure=55,
            leadership_gap=50,
            composite=62,
        )
        db.add(snap_today)
        db.add(snap_prev)
        db.commit()

        response = api_client.get("/api/watchlist")
        assert response.status_code == 200
        data = response.json()
        # Find our DeltaCo in the list (db may have other entries from other tests)
        our_item = next(
            (i for i in data["items"] if i["company_id"] == company.id), None
        )
        assert our_item is not None
        assert our_item["company_name"] == "DeltaCo"
        assert our_item["latest_composite"] == 72
        assert our_item["delta_7d"] == 10  # 72 - 62


class TestWatchlistAuth:
    """Tests that watchlist endpoints require authentication."""

    def test_watchlist_endpoints_require_auth(self, db: Session) -> None:
        """POST, DELETE, GET without auth return 401."""
        from app.main import app
        from app.db.session import get_db

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        # Do NOT override require_auth — requests will get 401
        client = TestClient(app)

        company = Company(name="AuthCo", website_url="https://auth.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        r_post = client.post("/api/watchlist", json={"company_id": company.id})
        assert r_post.status_code == 401

        r_get = client.get("/api/watchlist")
        assert r_get.status_code == 401

        r_del = client.delete(f"/api/watchlist/{company.id}")
        assert r_del.status_code == 401

        app.dependency_overrides.clear()
