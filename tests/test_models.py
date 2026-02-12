"""SQLAlchemy model tests."""

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models import Company, JobRun, SignalRecord


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


def test_signal_record_model_creation() -> None:
    """SignalRecord model can be instantiated with company_id."""
    company = Company(name="Test Co", website_url="https://test.example.com")
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
