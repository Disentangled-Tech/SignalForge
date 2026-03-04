"""API tests for GET /api/outreach/recommendation/{company_id} (Issue #122 M2)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Company, OutreachRecommendation, ReadinessSnapshot, SignalPack
from app.models.user import User
from app.models.user_workspace import UserWorkspace
from app.models.workspace import Workspace
from app.pipeline.stages import DEFAULT_WORKSPACE_ID

_REC_AS_OF = date(2099, 3, 1)
FORBIDDEN_WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def api_client(db: Session) -> TestClient:
    """TestClient with real DB and mocked auth (Issue #122 M2)."""
    from app.api.deps import require_auth
    from app.db.session import get_db
    from app.main import app

    def override_get_db():
        yield db

    def override_auth():
        pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = override_auth
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _seed_company_with_snapshot_and_recommendation(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    recommendation_type: str = "Soft Value Share",
    outreach_score: int = 41,
    playbook_id: str = "fractional_cto_standard_v1",
) -> None:
    """Create Company, ReadinessSnapshot, and OutreachRecommendation for API tests."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        company = Company(
            name="RecAPI Co",
            website_url="https://recapi.example.com",
            founder_name="Founder",
        )
        db.add(company)
        db.flush()
    rs = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            ReadinessSnapshot.as_of == as_of,
            ReadinessSnapshot.pack_id == pack.id,
        )
        .first()
    )
    if not rs:
        rs = ReadinessSnapshot(
            company_id=company_id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=80,
            pack_id=pack.id,
        )
        db.add(rs)
        db.flush()
    existing = (
        db.query(OutreachRecommendation)
        .filter(
            OutreachRecommendation.company_id == company_id,
            OutreachRecommendation.as_of == as_of,
            OutreachRecommendation.pack_id == pack.id,
        )
        .first()
    )
    if not existing:
        rec = OutreachRecommendation(
            company_id=company_id,
            as_of=as_of,
            recommendation_type=recommendation_type,
            outreach_score=outreach_score,
            channel="LinkedIn DM",
            draft_variants=[{"subject": "Test", "message": "Hello"}],
            safeguards_triggered=None,
            generation_version="1",
            pack_id=pack.id,
            playbook_id=playbook_id,
        )
        db.add(rec)
    db.commit()


class TestOutreachRecommendationAPI:
    """GET /api/outreach/recommendation/{company_id} endpoint."""

    def test_returns_200_and_response_shape_when_company_and_snapshot_exist(
        self,
        db: Session,
        api_client: TestClient,
    ) -> None:
        """Valid company and snapshot return 200 and OutreachRecommendationResponse shape."""
        company = Company(
            name="RecCo",
            website_url="https://recco.example.com",
            founder_name="Jane",
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        _seed_company_with_snapshot_and_recommendation(db, company.id, _REC_AS_OF)
        url = f"/api/outreach/recommendation/{company.id}?as_of={_REC_AS_OF.isoformat()}"
        resp = api_client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_id"] == company.id
        assert data["as_of"] == _REC_AS_OF.isoformat()
        assert "recommended_playbook_id" in data
        assert "drafts" in data
        assert isinstance(data["drafts"], list)
        assert "rationale" in data
        assert "recommendation_type" in data
        assert "outreach_score" in data
        assert data["recommendation_type"] == "Soft Value Share"
        assert data["outreach_score"] == 41

    def test_returns_404_when_company_missing(
        self,
        api_client: TestClient,
    ) -> None:
        """Non-existent company_id returns 404."""
        resp = api_client.get("/api/outreach/recommendation/999999")
        assert resp.status_code == 404
        assert "not found" in resp.json().get("detail", "").lower()

    def test_returns_404_when_no_snapshot_for_as_of(
        self,
        db: Session,
        api_client: TestClient,
    ) -> None:
        """Valid company but as_of with no snapshot returns 404."""
        company = Company(
            name="NoSnapshotCo",
            website_url="https://nosnap.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        # No ReadinessSnapshot for 2020-01-01
        resp = api_client.get(f"/api/outreach/recommendation/{company.id}?as_of=2020-01-01")
        assert resp.status_code == 404
        assert "not found" in resp.json().get("detail", "").lower()

    def test_recommendation_requires_auth(self, client: TestClient) -> None:
        """GET /api/outreach/recommendation/{id} without auth returns 401."""
        resp = client.get("/api/outreach/recommendation/1")
        assert resp.status_code == 401

    @patch("app.api.deps.get_settings")
    @patch("app.api.outreach.get_settings")
    def test_returns_403_when_user_lacks_workspace_access(
        self,
        mock_outreach_settings: MagicMock,
        mock_deps_settings: MagicMock,
        db: Session,
    ) -> None:
        """With multi_workspace_enabled, user without access to workspace_id gets 403 (Issue #122)."""
        from app.api.deps import require_auth
        from app.db.session import get_db
        from app.main import app

        # Workspace the user will not have access to
        forbidden_ws = Workspace(id=UUID(FORBIDDEN_WORKSPACE_ID), name="Forbidden Workspace")
        db.add(forbidden_ws)
        db.flush()

        user = User(username="ws_test_user")
        user.set_password("testpass")
        db.add(user)
        db.flush()
        db.refresh(user)
        db.add(UserWorkspace(user_id=user.id, workspace_id=UUID(DEFAULT_WORKSPACE_ID)))
        db.commit()

        company = Company(
            name="403TestCo",
            website_url="https://403test.example.com",
            founder_name="Founder",
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        _seed_company_with_snapshot_and_recommendation(db, company.id, _REC_AS_OF)

        def override_get_db():
            yield db

        def override_auth():
            return user

        mock_settings = MagicMock()
        mock_settings.multi_workspace_enabled = True
        mock_outreach_settings.return_value = mock_settings
        mock_deps_settings.return_value = mock_settings

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_auth] = override_auth
        try:
            client = TestClient(app)
            url = f"/api/outreach/recommendation/{company.id}?as_of={_REC_AS_OF.isoformat()}&workspace_id={FORBIDDEN_WORKSPACE_ID}"
            resp = client.get(url)
            assert resp.status_code == 403
            assert "workspace" in resp.json().get("detail", "").lower()
        finally:
            app.dependency_overrides.clear()
