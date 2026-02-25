"""Tests for briefing page HTML routes."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure env vars are set before importing app modules
from tests.test_constants import (
    TEST_INTERNAL_JOB_TOKEN,
    TEST_SECRET_KEY,
    TEST_USERNAME_VIEWS,
)

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://localhost:5432/signalforge_test")
os.environ.setdefault("SECRET_KEY", TEST_SECRET_KEY)
os.environ.setdefault("INTERNAL_JOB_TOKEN", TEST_INTERNAL_JOB_TOKEN)

from app.api.briefing_views import router  # noqa: E402
from app.api.deps import get_db, require_ui_auth  # noqa: E402
from app.models.analysis_record import AnalysisRecord  # noqa: E402
from app.models.briefing_item import BriefingItem  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.job_run import JobRun  # noqa: E402
from app.models.user import User  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────


def _make_user() -> MagicMock:
    """Create a mock User."""
    user = MagicMock(spec=User)
    user.id = 1
    user.username = TEST_USERNAME_VIEWS
    return user


def _make_company(id: int = 1, **overrides) -> MagicMock:
    """Create a mock Company."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=id, name="Acme Corp", website_url="https://acme.example.com",
        founder_name="Jane Doe", founder_linkedin_url=None,
        company_linkedin_url=None, source="manual",
        target_profile_match=False, current_stage="mvp_building",
        notes=None, cto_need_score=85, created_at=now,
        updated_at=now, last_scan_at=None,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=Company)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_analysis(id: int = 1, **overrides) -> MagicMock:
    """Create a mock AnalysisRecord."""
    defaults = dict(
        id=id, company_id=1, source_type="full_analysis",
        stage="mvp_building", stage_confidence=80,
        pain_signals_json={}, evidence_bullets=[],
        explanation="Test explanation",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    mock = MagicMock(spec=AnalysisRecord)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_briefing_item(id: int = 1, **overrides) -> MagicMock:
    """Create a mock BriefingItem with company and analysis."""
    company = overrides.pop("company", _make_company())
    analysis = overrides.pop("analysis", _make_analysis())
    defaults = dict(
        id=id, company_id=company.id, analysis_id=analysis.id,
        why_now="Recent funding round",
        risk_summary="Early stage, may not convert",
        suggested_angle="Technical advisor for scaling",
        outreach_subject="Congrats on the raise",
        outreach_message="Hi Jane, I noticed your company just raised.",
        briefing_date=date.today(),
        created_at=datetime.now(timezone.utc),
        company=company, analysis=analysis,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=BriefingItem)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _create_test_app(mock_db, mock_user=None):
    """Create a FastAPI app with briefing router and mocked deps."""
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    if mock_user is not None:
        app.dependency_overrides[require_ui_auth] = lambda: mock_user

    return app


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def mock_user():
    return _make_user()


@pytest.fixture
def auth_client(mock_db, mock_user):
    """Authenticated test client with mocked DB."""
    app = _create_test_app(mock_db, mock_user)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def noauth_client(mock_db):
    """Unauthenticated test client — no auth override."""
    app = _create_test_app(mock_db)
    return TestClient(app, raise_server_exceptions=False)


# ── Tests ────────────────────────────────────────────────────────────


class TestBriefingPage:
    """Tests for GET /briefing."""

    @patch("app.api.briefing_views.get_briefing_data")
    def test_briefing_renders_with_items(
        self, mock_get_data, mock_db, mock_user
    ):
        """Briefing page renders when items exist."""
        item = _make_briefing_item()
        mock_get_data.return_value = {
            "items": [item],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Acme Corp" in resp.text
        assert "Jane Doe" in resp.text
        assert "Daily Briefing" in resp.text
        assert "Congrats on the raise" in resp.text
        assert "Copy Outreach" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_main_card_shows_esl_when_available(
        self, mock_get_data, mock_db, mock_user
    ):
        """Main briefing card shows ESL badges when EngagementSnapshot exists (Issue #110)."""
        co = _make_company(id=1)
        item = _make_briefing_item(company=co)
        mock_get_data.return_value = {
            "items": [item],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {
                1: {
                    "esl_score": 0.75,
                    "outreach_score": 62,
                    "engagement_type": "Low-Pressure Intro",
                    "cadence_blocked": False,
                    "stability_cap_triggered": False,
                },
            },
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Low-Pressure Intro" in resp.text
        assert "Outreach: 62" in resp.text
        assert "ESL 0.75" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_briefing_empty_state(self, mock_get_data, mock_db, mock_user):
        """Briefing page shows empty state when no items."""
        mock_get_data.return_value = {
            "items": [],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "No briefing" in resp.text
        assert "Generate Now" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_briefing_shows_failure_alert_when_job_had_failures(
        self, mock_get_data, mock_db, mock_user
    ):
        """When latest briefing job had failures, show alert banner (issue #32)."""
        item = _make_briefing_item()
        mock_get_data.return_value = {
            "items": [item],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        job_with_error = MagicMock(spec=JobRun)
        job_with_error.status = "completed"
        job_with_error.error_message = "Company 1 (Acme): failed"
        job_run_chain = MagicMock()
        job_run_chain.filter.return_value = job_run_chain
        job_run_chain.order_by.return_value = job_run_chain
        job_run_chain.first.return_value = job_with_error
        mock_db.query.return_value = job_run_chain

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Last briefing job had failures" in resp.text
        assert "Settings" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_briefing_multiple_items_ordered(
        self, mock_get_data, mock_db, mock_user
    ):
        """Briefing page renders multiple items."""
        co1 = _make_company(id=1, name="Alpha Co", cto_need_score=90)
        co2 = _make_company(id=2, name="Beta Co", cto_need_score=60)
        item1 = _make_briefing_item(id=1, company=co1)
        item2 = _make_briefing_item(id=2, company=co2)
        mock_get_data.return_value = {
            "items": [item1, item2],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Alpha Co" in resp.text
        assert "Beta Co" in resp.text


class TestBriefingByDate:
    """Tests for GET /briefing/{date_str}."""

    @patch("app.api.briefing_views.get_briefing_data")
    def test_date_specific_briefing(
        self, mock_get_data, mock_db, mock_user
    ):
        """Briefing page renders for a specific date."""
        target = date(2026, 1, 15)
        item = _make_briefing_item(briefing_date=target)
        mock_get_data.return_value = {
            "items": [item],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing/2026-01-15")

        assert resp.status_code == 200
        assert "January 15, 2026" in resp.text

    def test_invalid_date_redirects(self, mock_db, mock_user):
        """Invalid date string redirects to /briefing."""
        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing/not-a-date", follow_redirects=False)

        assert resp.status_code == 302
        assert "/briefing" in resp.headers["location"]


class TestBriefingGenerate:
    """Tests for POST /briefing/generate."""

    def test_generate_calls_service_and_redirects(self, mock_db, mock_user):
        """Generate endpoint calls briefing service and redirects (issue #32)."""
        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)

        # Mock JobRun query: no error_message -> success redirect
        job_without_error = MagicMock(spec=JobRun)
        job_without_error.error_message = None
        job_run_chain = MagicMock()
        job_run_chain.filter.return_value = job_run_chain
        job_run_chain.order_by.return_value = job_run_chain
        job_run_chain.first.return_value = job_without_error
        mock_db.query.return_value.filter.return_value.order_by.return_value = job_run_chain

        with patch("app.api.briefing_views.generate_briefing", create=True) as mock_gen:
            resp = client.post("/briefing/generate", follow_redirects=False)

        assert resp.status_code == 303
        assert "/briefing" in resp.headers["location"]
        assert "error" not in resp.headers.get("location", "")

    def test_generate_with_partial_failures_redirects_with_error(self, mock_db, mock_user):
        """When briefing has partial failures, redirect with error param (issue #32)."""
        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)

        job_with_error = MagicMock(spec=JobRun)
        job_with_error.error_message = "Company 1 (Acme): LLM failed"
        job_run_chain = MagicMock()
        job_run_chain.first.return_value = job_with_error
        mock_db.query.return_value.filter.return_value.order_by.return_value = job_run_chain

        with patch("app.api.briefing_views.generate_briefing", create=True) as mock_gen:
            resp = client.post("/briefing/generate", follow_redirects=False)

        assert resp.status_code == 303
        assert "error=" in resp.headers.get("location", "")
        assert "Partial" in resp.headers.get("location", "") or "failures" in resp.headers.get("location", "")

    def test_generate_import_error_redirects_with_error(self, mock_db, mock_user):
        """When service not available, redirects with error."""
        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)

        # Ensure the import fails by removing the module
        import sys
        saved = sys.modules.pop("app.services.briefing", None)
        try:
            with patch.dict("sys.modules", {"app.services.briefing": None}):
                # This should cause ImportError when route tries to import
                resp = client.post("/briefing/generate", follow_redirects=False)
        finally:
            if saved is not None:
                sys.modules["app.services.briefing"] = saved

        assert resp.status_code == 303
        assert "error" in resp.headers["location"]


class TestBriefingDisplayScores:
    """Tests for CTO Score display (Issue #24: same logic as company detail)."""

    @patch("app.api.briefing_views.get_briefing_data")
    def test_briefing_uses_display_scores_when_available(
        self, mock_get_data, mock_db, mock_user
    ):
        """Briefing page shows recomputed score from get_display_scores_for_companies."""
        co = _make_company(id=1, cto_need_score=70)  # stored score
        item = _make_briefing_item(company=co)
        mock_get_data.return_value = {
            "items": [item],
            "emerging_companies": [],
            "display_scores": {1: 88},  # recomputed score
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "88" in resp.text
        assert "CTO Score" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_briefing_falls_back_to_stored_score_when_no_recomputed(
        self, mock_get_data, mock_db, mock_user
    ):
        """When get_display_scores returns empty, use company.cto_need_score."""
        co = _make_company(id=1, cto_need_score=75)
        item = _make_briefing_item(company=co)
        mock_get_data.return_value = {
            "items": [item],
            "emerging_companies": [],
            "display_scores": {},  # no recomputed scores
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "75" in resp.text


class TestBriefingSort:
    """Tests for sort/filter param (Issue #24)."""

    @patch("app.api.briefing_views.get_briefing_data")
    def test_sort_param_score_orders_by_cto_score(
        self, mock_get_data, mock_db, mock_user
    ):
        """sort=score uses cto_need_score desc (default)."""
        item = _make_briefing_item()
        mock_get_data.return_value = {
            "items": [item],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/briefing?sort=score")

        mock_get_data.assert_called_once()
        assert mock_get_data.call_args[0][2] == "score"

    @patch("app.api.briefing_views.get_briefing_data")
    def test_sort_param_invalid_falls_back_to_score(self, mock_get_data, mock_db, mock_user):
        """Invalid sort value does not cause 500; falls back to score."""
        mock_get_data.return_value = {
            "items": [],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing?sort=invalid")

        assert resp.status_code == 200

    @patch("app.api.briefing_views.get_briefing_data")
    def test_sort_param_outreach_score_returns_200(
        self, mock_get_data, mock_db, mock_user
    ):
        """sort=outreach_score renders without error (Issue #103)."""
        item = _make_briefing_item()
        mock_get_data.return_value = {
            "items": [item],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing?sort=outreach_score")

        assert resp.status_code == 200
        assert "outreach_score" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_duplicate_companies_deduplicated_in_display(
        self, mock_get_data, mock_db, mock_user
    ):
        """When same company has multiple BriefingItems, display shows only one."""
        co = _make_company(id=1, name="Acme Corp")
        item1 = _make_briefing_item(
            id=1, company=co, risk_summary="First risk", created_at=datetime(2026, 2, 17, 8, 0, tzinfo=timezone.utc)
        )
        # get_briefing_data deduplicates; we simulate it returning one item
        mock_get_data.return_value = {
            "items": [item1],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert resp.text.count("Acme Corp") == 1

    @patch("app.api.briefing_views.get_briefing_data")
    def test_sort_ui_present_when_items_exist(
        self, mock_get_data, mock_db, mock_user
    ):
        """Sort dropdown/links visible when briefing has items."""
        item = _make_briefing_item()
        mock_get_data.return_value = {
            "items": [item],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "sort=" in resp.text or "Sort" in resp.text


class TestEmergingCompaniesSection:
    """Tests for Emerging Companies to Watch section (Issue #93)."""

    @patch("app.api.briefing_views.get_briefing_data")
    def test_briefing_page_includes_emerging_section(
        self, mock_get_data, mock_db, mock_user
    ):
        """When emerging companies exist, section shows OutreachScore and ESL (Issue #102)."""
        co = MagicMock()
        co.id = 1
        co.name = "Emerging Corp"
        co.website_url = "https://emerging.example.com"
        snap = MagicMock()
        snap.composite = 72
        snap.momentum = 70
        snap.complexity = 65
        snap.pressure = 60
        snap.leadership_gap = 55
        snap.explain = {"top_events": [{"event_type": "funding_raised"}]}
        eng_snap = MagicMock()
        eng_snap.esl_score = 1.0
        eng_snap.engagement_type = "Standard Outreach"
        eng_snap.cadence_blocked = False
        eng_snap.explain = {}
        mock_get_data.return_value = {
            "items": [],
            "emerging_companies": [{
                "company": co,
                "snapshot": snap,
                "engagement_snapshot": eng_snap,
                "outreach_score": 72,
                "esl_score": 1.0,
                "engagement_type": "Standard Outreach",
                "cadence_blocked": False,
                "stability_cap_triggered": False,
                "top_signals": ["New funding"],
            }],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Emerging Companies to Watch" in resp.text
        assert "Emerging Corp" in resp.text
        assert "Outreach: 72" in resp.text
        assert "Standard Outreach" in resp.text
        assert "New funding" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_briefing_page_emerging_empty_state(
        self, mock_get_data, mock_db, mock_user
    ):
        """When no snapshots, emerging section shows empty message."""
        mock_get_data.return_value = {
            "items": [],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Emerging Companies to Watch" in resp.text
        assert "No emerging companies for this date" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_emerging_section_shows_esl_and_cooldown(
        self, mock_get_data, mock_db, mock_user
    ):
        """Emerging section displays ESL score, recommendation category, cooldown badge."""
        co = MagicMock()
        co.id = 2
        co.name = "Cooldown Co"
        co.website_url = "https://cooldown.example.com"
        snap = MagicMock()
        snap.composite = 60
        snap.momentum = 50
        snap.complexity = 55
        snap.pressure = 50
        snap.leadership_gap = 45
        snap.explain = {}
        eng_snap = MagicMock()
        eng_snap.esl_score = 0.5
        eng_snap.engagement_type = "Observe Only"
        eng_snap.cadence_blocked = True
        eng_snap.explain = {}
        mock_get_data.return_value = {
            "items": [],
            "emerging_companies": [{
                "company": co,
                "snapshot": snap,
                "engagement_snapshot": eng_snap,
                "outreach_score": 30,
                "esl_score": 0.5,
                "engagement_type": "Observe Only",
                "cadence_blocked": True,
                "stability_cap_triggered": False,
                "top_signals": [],
            }],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Observe Only" in resp.text
        assert "Cooldown active" in resp.text
        assert "Outreach: 30" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_emerging_section_shows_recommendation_band_when_pack_defines(
        self, mock_get_data, mock_db, mock_user
    ):
        """Emerging section displays recommendation_band badge when pack defines bands (Issue #242 Phase 3)."""
        co = MagicMock()
        co.id = 3
        co.name = "BandCo"
        co.website_url = "https://bandco.example.com"
        snap = MagicMock()
        snap.composite = 80
        snap.momentum = 75
        snap.complexity = 70
        snap.pressure = 65
        snap.leadership_gap = 60
        snap.explain = {"recommendation_band": "HIGH_PRIORITY"}
        eng_snap = MagicMock()
        eng_snap.esl_score = 1.0
        eng_snap.engagement_type = "Standard Outreach"
        eng_snap.cadence_blocked = False
        eng_snap.explain = {}
        mock_get_data.return_value = {
            "items": [],
            "emerging_companies": [{
                "company": co,
                "snapshot": snap,
                "engagement_snapshot": eng_snap,
                "outreach_score": 80,
                "esl_score": 1.0,
                "engagement_type": "Standard Outreach",
                "cadence_blocked": False,
                "stability_cap_triggered": False,
                "top_signals": [],
                "recommendation_band": "HIGH_PRIORITY",
            }],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "HIGH_PRIORITY" in resp.text
        assert "BandCo" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_emerging_section_shows_stability_cap_badge(
        self, mock_get_data, mock_db, mock_user
    ):
        """When stability_cap_triggered in explain, show Stability cap badge (Issue #111)."""
        co = MagicMock()
        co.id = 3
        co.name = "StabilityCap Co"
        co.website_url = "https://stability.example.com"
        snap = MagicMock()
        snap.composite = 75
        snap.momentum = 70
        snap.complexity = 65
        snap.pressure = 70
        snap.leadership_gap = 60
        snap.explain = {}
        eng_snap = MagicMock()
        eng_snap.esl_score = 0.5
        eng_snap.engagement_type = "Soft Value Share"
        eng_snap.cadence_blocked = False
        eng_snap.explain = {"stability_cap_triggered": True}
        mock_get_data.return_value = {
            "items": [],
            "emerging_companies": [{
                "company": co,
                "snapshot": snap,
                "engagement_snapshot": eng_snap,
                "outreach_score": 37,
                "esl_score": 0.5,
                "engagement_type": "Soft Value Share",
                "cadence_blocked": False,
                "stability_cap_triggered": True,
                "top_signals": [],
            }],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Stability cap — Soft Value Share only" in resp.text
        assert "Soft Value Share" in resp.text

    @patch("app.api.briefing_views.get_briefing_data")
    def test_emerging_section_does_not_affect_existing_briefing(
        self, mock_get_data, mock_db, mock_user
    ):
        """Existing BriefingItem section unchanged when emerging section added."""
        item = _make_briefing_item()
        mock_get_data.return_value = {
            "items": [item],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }

        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing")

        assert resp.status_code == 200
        assert "Acme Corp" in resp.text
        assert "Daily Briefing" in resp.text
        assert "Congrats on the raise" in resp.text


@patch("app.api.briefing_views.get_settings")
@patch("app.api.briefing_views.get_briefing_data")
class TestMultiWorkspaceBriefing:
    """Tests for multi-workspace briefing (workspace_id scoping, validation)."""

    def test_invalid_workspace_id_returns_422(
        self, mock_get_data, mock_settings, mock_db, mock_user
    ):
        """When multi_workspace_enabled and workspace_id invalid, return 422."""
        mock_settings.return_value = MagicMock(multi_workspace_enabled=True)
        mock_get_data.return_value = {
            "items": [],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }
        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/briefing?workspace_id=not-a-uuid")
        assert resp.status_code == 422
        mock_get_data.assert_not_called()

    def test_valid_workspace_id_scopes_briefing(
        self, mock_get_data, mock_settings, mock_db, mock_user
    ):
        """When multi_workspace_enabled and valid workspace_id, get_briefing_data called with it."""
        mock_settings.return_value = MagicMock(multi_workspace_enabled=True)
        mock_get_data.return_value = {
            "items": [],
            "emerging_companies": [],
            "display_scores": {},
            "esl_by_company": {},
        }
        app = _create_test_app(mock_db, mock_user)
        client = TestClient(app, raise_server_exceptions=False)
        ws_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = client.get(f"/briefing?workspace_id={ws_uuid}")
        assert resp.status_code == 200
        mock_get_data.assert_called_once()
        call_kwargs = mock_get_data.call_args[1]
        assert call_kwargs["workspace_id"] == ws_uuid


class TestAuthRequired:
    """Tests that routes require authentication."""

    def test_briefing_requires_auth(self, noauth_client):
        """GET /briefing redirects to login without authentication."""
        resp = noauth_client.get("/briefing", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"

    def test_briefing_date_requires_auth(self, noauth_client):
        """GET /briefing/{date} redirects to login without authentication."""
        resp = noauth_client.get("/briefing/2026-01-01", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"

    def test_generate_requires_auth(self, noauth_client):
        """POST /briefing/generate redirects to login without authentication."""
        resp = noauth_client.post("/briefing/generate", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"
