"""SQLAlchemy model tests."""

from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from app.models import (
    AnalysisRecord,
    AppSettings,
    BriefingItem,
    Company,
    JobRun,
    OperatorProfile,
    SignalRecord,
    User,
)


def test_company_model_creation() -> None:
    """Company model can be instantiated with expected attributes."""
    company = Company(
        name="Acme Corp",
        website_url="https://acme.example.com",
        founder_name="Jane Doe",
        notes="Early stage",
    )
    assert company.name == "Acme Corp"
    assert company.website_url == "https://acme.example.com"
    assert company.founder_name == "Jane Doe"
    assert company.notes == "Early stage"
    assert company.cto_need_score is None
    assert company.last_scan_at is None


def test_company_new_fields_nullable() -> None:
    """Company model has nullable new fields defaulting to None."""
    company = Company(name="NewCo")
    assert company.founder_linkedin_url is None
    assert company.company_linkedin_url is None
    assert company.current_stage is None


def test_company_new_fields_defaults(db: Session) -> None:
    """Company model DB defaults for source and target_profile_match."""
    company = Company(name="DefaultCo")
    db.add(company)
    db.commit()
    db.refresh(company)
    assert company.source == "manual"
    assert company.target_profile_match is False


def test_company_new_fields_with_values() -> None:
    """Company model accepts all new field values."""
    company = Company(
        name="FullCo",
        founder_linkedin_url="https://linkedin.com/in/founder",
        company_linkedin_url="https://linkedin.com/company/fullco",
        source="referral",
        target_profile_match=True,
        current_stage="mvp_building",
    )
    assert company.founder_linkedin_url == "https://linkedin.com/in/founder"
    assert company.company_linkedin_url == "https://linkedin.com/company/fullco"
    assert company.source == "referral"
    assert company.target_profile_match is True
    assert company.current_stage == "mvp_building"


def test_signal_record_model_creation() -> None:
    """SignalRecord model can be instantiated with company_id."""
    signal = SignalRecord(
        company_id=1,
        source_url="https://test.example.com/blog",
        content_hash="abc123",
        content_text="Sample content",
    )
    assert signal.company_id == 1
    assert signal.source_url == "https://test.example.com/blog"
    assert signal.content_hash == "abc123"
    assert signal.content_text == "Sample content"
    assert signal.source_type is None


def test_signal_record_source_type() -> None:
    """SignalRecord model accepts source_type field."""
    signal = SignalRecord(
        company_id=1,
        source_url="https://example.com/careers",
        content_hash="def456",
        content_text="Hiring engineers",
        source_type="careers",
    )
    assert signal.source_type == "careers"


def test_job_run_model_creation() -> None:
    """JobRun model can be instantiated with expected attributes."""
    job = JobRun(
        job_type="scan",
        status="running",
    )
    assert job.job_type == "scan"
    assert job.status == "running"
    assert job.companies_processed is None
    assert job.error_message is None
    assert job.finished_at is None


def test_analysis_record_model_creation() -> None:
    """AnalysisRecord model can be instantiated with expected attributes."""
    record = AnalysisRecord(
        company_id=1,
        source_type="stage_classification",
        stage="mvp_building",
        stage_confidence=85,
        pain_signals_json={"hiring": True, "scaling": False},
        evidence_bullets=["Hiring 3 engineers", "Series A raised"],
        explanation="Company is building MVP and hiring aggressively.",
        raw_llm_response='{"stage": "mvp_building"}',
    )
    assert record.company_id == 1
    assert record.source_type == "stage_classification"
    assert record.stage == "mvp_building"
    assert record.stage_confidence == 85
    assert record.pain_signals_json == {"hiring": True, "scaling": False}
    assert record.evidence_bullets == ["Hiring 3 engineers", "Series A raised"]
    assert record.explanation == "Company is building MVP and hiring aggressively."
    assert record.raw_llm_response == '{"stage": "mvp_building"}'


def test_briefing_item_model_creation() -> None:
    """BriefingItem model can be instantiated with expected attributes."""
    item = BriefingItem(
        company_id=1,
        analysis_id=1,
        why_now="Recent funding round",
        risk_summary="Early stage, may not convert",
        suggested_angle="Technical advisor for scaling",
        outreach_subject="Congrats on the raise",
        outreach_message="Hi Jane, I noticed...",
        briefing_date=date(2026, 2, 12),
    )
    assert item.company_id == 1
    assert item.analysis_id == 1
    assert item.why_now == "Recent funding round"
    assert item.risk_summary == "Early stage, may not convert"
    assert item.suggested_angle == "Technical advisor for scaling"
    assert item.outreach_subject == "Congrats on the raise"
    assert item.outreach_message == "Hi Jane, I noticed..."
    assert item.briefing_date == date(2026, 2, 12)


def test_user_model_creation() -> None:
    """User model can be instantiated and hash/verify passwords."""
    user = User(username="admin")
    user.set_password("secret123")
    assert user.username == "admin"
    assert user.password_hash is not None
    assert user.password_hash != "secret123"
    assert user.verify_password("secret123") is True
    assert user.verify_password("wrong") is False


def test_operator_profile_model_creation() -> None:
    """OperatorProfile model can be instantiated."""
    profile = OperatorProfile(content="# My Profile\nFractional CTO with 15 years experience.")
    assert profile.content == "# My Profile\nFractional CTO with 15 years experience."


def test_app_settings_model_creation() -> None:
    """AppSettings model can be instantiated."""
    setting = AppSettings(key="briefing_time", value="07:00")
    assert setting.key == "briefing_time"
    assert setting.value == "07:00"


def test_company_signal_record_relationship(db: Session) -> None:
    """Company and SignalRecord have correct relationship."""
    company = Company(name="Rel Co", website_url="https://rel.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    signal = SignalRecord(
        company_id=company.id,
        source_url="https://rel.example.com/news",
        content_hash="hash1",
        content_text="News content",
    )
    db.add(signal)
    db.commit()

    db.refresh(company)
    assert len(company.signal_records) == 1
    assert company.signal_records[0].content_hash == "hash1"


def test_company_analysis_record_relationship(db: Session) -> None:
    """Company and AnalysisRecord have correct relationship."""
    company = Company(name="Analysis Co", website_url="https://analysis.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    analysis = AnalysisRecord(
        company_id=company.id,
        source_type="stage_classification",
        stage="early_customers",
        stage_confidence=70,
    )
    db.add(analysis)
    db.commit()

    db.refresh(company)
    assert len(company.analysis_records) == 1
    assert company.analysis_records[0].stage == "early_customers"


def test_company_briefing_item_relationship(db: Session) -> None:
    """Company → AnalysisRecord → BriefingItem relationship chain works."""
    company = Company(name="Briefing Co", website_url="https://brief.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    analysis = AnalysisRecord(
        company_id=company.id,
        source_type="pain_signals",
        stage="scaling_team",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    item = BriefingItem(
        company_id=company.id,
        analysis_id=analysis.id,
        why_now="Rapid hiring",
        outreach_subject="CTO help",
    )
    db.add(item)
    db.commit()

    db.refresh(company)
    db.refresh(analysis)
    assert len(company.briefing_items) == 1
    assert company.briefing_items[0].why_now == "Rapid hiring"
    assert len(analysis.briefing_items) == 1
    assert analysis.briefing_items[0].outreach_subject == "CTO help"
