"""Tests for outreach history API (Issue #114)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.outreach_history import OutreachHistory
from app.services.outreach_history import create_outreach_record


@pytest.fixture
def api_client(db: Session, client: TestClient) -> TestClient:
    """TestClient with real DB and auth bypass."""
    from app.main import app
    from app.api.deps import get_db, require_auth

    def override_get_db():
        yield db

    async def override_auth():
        pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = override_auth
    yield client
    app.dependency_overrides.clear()


def test_get_company_outreach_returns_records(api_client: TestClient, db: Session):
    """GET /api/companies/{id}/outreach returns outreach history with new fields."""
    company = Company(name="API Outreach Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    sent_at = datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
    create_outreach_record(
        db,
        company_id=company.id,
        sent_at=sent_at,
        outreach_type="email",
        message="Test message",
        notes="Test notes",
        outcome="replied",
        timing_quality_feedback="good_timing",
    )

    resp = api_client.get(f"/api/companies/{company.id}/outreach")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["outcome"] == "replied"
    assert item["timing_quality_feedback"] == "good_timing"
    assert item["notes"] == "Test notes"
    assert item["outreach_type"] == "email"
    assert "sent_at" in item
    assert "created_at" in item


def test_get_company_outreach_not_found(api_client: TestClient, db: Session):
    """GET /api/companies/99999/outreach returns 404 when company missing."""
    resp = api_client.get("/api/companies/99999/outreach")
    assert resp.status_code == 404


def test_patch_outreach_updates_fields(api_client: TestClient, db: Session):
    """PATCH /api/companies/{id}/outreach/{outreach_id} updates outcome, notes, timing."""
    company = Company(name="Patch Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    base = datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=base - timedelta(days=70),
        outreach_type="email",
        message=None,
        notes=None,
    )
    assert record.outcome is None
    assert record.notes is None
    assert record.timing_quality_feedback is None

    resp = api_client.patch(
        f"/api/companies/{company.id}/outreach/{record.id}",
        json={
            "outcome": "replied",
            "notes": "Scheduled follow-up",
            "timing_quality_feedback": "neutral",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "replied"
    assert data["notes"] == "Scheduled follow-up"
    assert data["timing_quality_feedback"] == "neutral"


def test_patch_outreach_not_found(api_client: TestClient, db: Session):
    """PATCH returns 404 when outreach record not found."""
    company = Company(name="No Outreach Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    resp = api_client.patch(
        f"/api/companies/{company.id}/outreach/99999",
        json={"outcome": "replied"},
    )
    assert resp.status_code == 404


def test_patch_outreach_invalid_outcome(api_client: TestClient, db: Session):
    """PATCH returns 422 when outcome is invalid."""
    company = Company(name="Invalid Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
        - timedelta(days=70),
        outreach_type="email",
        message=None,
        notes=None,
    )

    resp = api_client.patch(
        f"/api/companies/{company.id}/outreach/{record.id}",
        json={"outcome": "invalid_outcome"},
    )
    assert resp.status_code == 422


def test_patch_outreach_invalid_timing(api_client: TestClient, db: Session):
    """PATCH returns 422 when timing_quality_feedback is invalid."""
    company = Company(name="Invalid Timing Co", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    record = create_outreach_record(
        db,
        company_id=company.id,
        sent_at=datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
        - timedelta(days=70),
        outreach_type="email",
        message=None,
        notes=None,
    )

    resp = api_client.patch(
        f"/api/companies/{company.id}/outreach/{record.id}",
        json={"timing_quality_feedback": "invalid"},
    )
    assert resp.status_code == 422
