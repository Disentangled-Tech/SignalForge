"""Tests for Pydantic schemas — creation, validation, and rejection of bad data."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest
from pydantic import ValidationError

from app.schemas import (
    AnalysisRecordRead,
    BriefingItemRead,
    BriefingResponse,
    CompanyCreate,
    CompanyList,
    CompanyRead,
    CompanySource,
    CompanyUpdate,
    LoginRequest,
    OperatorProfileRead,
    OperatorProfileUpdate,
    PainSignalItem,
    PainSignals,
    SettingsRead,
    SettingsUpdate,
    SignalRecordRead,
    TokenResponse,
    UserRead,
)


# ── Company ──────────────────────────────────────────────────────────


class TestCompanyCreate:
    def test_valid_minimal(self) -> None:
        c = CompanyCreate(company_name="Acme Corp")
        assert c.company_name == "Acme Corp"
        assert c.source == CompanySource.manual

    def test_valid_full(self) -> None:
        c = CompanyCreate(
            company_name="Acme Corp",
            website_url="https://acme.example.com",
            founder_name="Jane Doe",
            founder_linkedin_url="https://linkedin.com/in/janedoe",
            company_linkedin_url="https://linkedin.com/company/acme",
            notes="Early stage startup",
            source=CompanySource.referral,
            target_profile_match="CTO needed",
        )
        assert c.source == CompanySource.referral
        assert c.founder_linkedin_url == "https://linkedin.com/in/janedoe"

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            CompanyCreate(company_name="")

    def test_rejects_missing_name(self) -> None:
        with pytest.raises(ValidationError):
            CompanyCreate()  # type: ignore[call-arg]

    def test_rejects_invalid_source(self) -> None:
        with pytest.raises(ValidationError):
            CompanyCreate(company_name="X", source="invalid")  # type: ignore[arg-type]


class TestCompanyUpdate:
    def test_all_optional(self) -> None:
        u = CompanyUpdate()
        assert u.company_name is None
        assert u.source is None

    def test_partial_update(self) -> None:
        u = CompanyUpdate(company_name="New Name", source=CompanySource.research)
        assert u.company_name == "New Name"
        assert u.source == CompanySource.research


class TestCompanyRead:
    def test_from_dict(self) -> None:
        now = datetime.now(timezone.utc)
        r = CompanyRead(
            id=1,
            company_name="Test",
            created_at=now,
        )
        assert r.id == 1
        assert r.cto_need_score is None

    def test_company_list(self) -> None:
        now = datetime.now(timezone.utc)
        item = CompanyRead(id=1, company_name="Co", created_at=now)
        cl = CompanyList(items=[item], total=1)
        assert cl.total == 1
        assert len(cl.items) == 1


# ── Signal ───────────────────────────────────────────────────────────


class TestSignalRecordRead:
    def test_valid(self) -> None:
        now = datetime.now(timezone.utc)
        s = SignalRecordRead(
            id=1,
            company_id=10,
            source_url="https://example.com/blog",
            content_text="Some text",
            created_at=now,
        )
        assert s.company_id == 10
        assert s.source_type is None


# ── Analysis ─────────────────────────────────────────────────────────


class TestPainSignals:
    def test_defaults(self) -> None:
        ps = PainSignals()
        assert ps.hiring_engineers.value is False
        assert ps.compliance_security_pressure.why == ""

    def test_custom_values(self) -> None:
        ps = PainSignals(
            hiring_engineers=PainSignalItem(value=True, why="3 open roles"),
        )
        assert ps.hiring_engineers.value is True
        assert ps.hiring_engineers.why == "3 open roles"


class TestAnalysisRecordRead:
    def test_valid(self) -> None:
        now = datetime.now(timezone.utc)
        a = AnalysisRecordRead(
            id=1,
            company_id=5,
            stage="growth",
            stage_confidence=0.85,
            pain_signals=PainSignals(),
            evidence_bullets=["bullet 1", "bullet 2"],
            explanation="Looks promising",
            created_at=now,
        )
        assert a.stage == "growth"
        assert a.stage_confidence == 0.85

    def test_rejects_confidence_out_of_range(self) -> None:
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            AnalysisRecordRead(
                id=1, company_id=5, stage_confidence=1.5, created_at=now
            )


# ── Briefing ─────────────────────────────────────────────────────────


class TestBriefingItemRead:
    def test_valid(self) -> None:
        now = datetime.now(timezone.utc)
        company = CompanyRead(id=1, company_name="Co", created_at=now)
        b = BriefingItemRead(
            id=1,
            company=company,
            stage="seed",
            why_now="Recent funding round",
            risk_summary="Low traction",
            suggested_angle="Technical leadership",
            outreach_subject="Quick question",
            outreach_message="Hi there...",
            briefing_date=date.today(),
        )
        assert b.company.company_name == "Co"
        assert b.why_now == "Recent funding round"


class TestBriefingResponse:
    def test_valid(self) -> None:
        br = BriefingResponse(date=date.today(), items=[], total=0)
        assert br.total == 0
        assert br.items == []


# ── Auth ─────────────────────────────────────────────────────────────


class TestLoginRequest:
    def test_valid(self) -> None:
        from tests.test_constants import TEST_PASSWORD

        lr = LoginRequest(username="admin", password=TEST_PASSWORD)
        assert lr.username == "admin"

    def test_rejects_empty_username(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(username="", password="x")

    def test_rejects_empty_password(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(username="admin", password="")

    def test_rejects_missing_fields(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest()  # type: ignore[call-arg]


class TestTokenResponse:
    def test_valid(self) -> None:
        from tests.test_constants import TEST_ACCESS_TOKEN_PLACEHOLDER

        t = TokenResponse(access_token=TEST_ACCESS_TOKEN_PLACEHOLDER)
        assert t.token_type == "bearer"


class TestUserRead:
    def test_valid(self) -> None:
        u = UserRead(id=1, username="admin")
        assert u.id == 1


# ── Settings ─────────────────────────────────────────────────────────


class TestSettingsUpdate:
    def test_all_optional(self) -> None:
        s = SettingsUpdate()
        assert s.briefing_time is None
        assert s.scoring_weights is None

    def test_with_values(self) -> None:
        s = SettingsUpdate(
            briefing_time=time(8, 0),
            briefing_email="user@example.com",
            scoring_weights={"hiring": 0.3, "funding": 0.5},
        )
        assert s.briefing_time == time(8, 0)
        assert s.scoring_weights["funding"] == 0.5


class TestSettingsRead:
    def test_valid(self) -> None:
        s = SettingsRead(
            briefing_time=time(9, 30),
            briefing_email="test@test.com",
            scoring_weights={"hiring": 1.0},
        )
        assert s.briefing_email == "test@test.com"


class TestOperatorProfile:
    def test_update_valid(self) -> None:
        op = OperatorProfileUpdate(content="# My Profile\nI'm a CTO...")
        assert "CTO" in op.content

    def test_update_rejects_empty(self) -> None:
        with pytest.raises(ValidationError):
            OperatorProfileUpdate(content="")

    def test_read_valid(self) -> None:
        now = datetime.now(timezone.utc)
        r = OperatorProfileRead(content="Profile text", updated_at=now)
        assert r.content == "Profile text"

