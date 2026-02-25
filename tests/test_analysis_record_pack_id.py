"""Tests for AnalysisRecord.pack_id (Phase 2, Plan Step 2)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models import AnalysisRecord, Company, SignalRecord
from app.services.analysis import analyze_company


def test_analysis_record_has_pack_id_column(db: Session) -> None:
    """AnalysisRecord has pack_id column (nullable)."""
    company = Company(name="Pack Co", website_url="https://pack.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    record = AnalysisRecord(
        company_id=company.id,
        source_type="full_analysis",
        stage="early_customers",
        pack_id=None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    assert record.pack_id is None


def test_analyze_company_sets_pack_id_when_pack_provided(db: Session) -> None:
    """analyze_company sets pack_id when pack is provided and default pack exists."""
    from app.services.pack_resolver import get_default_pack, get_default_pack_id

    pack_id = get_default_pack_id(db)
    if pack_id is None:
        pytest.skip("No default pack in DB (fractional_cto_v1 not installed)")

    company = Company(name="Analyze Co", website_url="https://analyze.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    # Add signal so analyze_company has content
    sig = SignalRecord(
        company_id=company.id,
        source_url="https://analyze.example.com/jobs",
        source_type="jobs",
        content_hash="abc123",
        content_text="We are hiring senior engineers.",
    )
    db.add(sig)
    db.commit()

    pack = get_default_pack(db)
    analysis = analyze_company(db, company.id, pack=pack)
    assert analysis is not None
    assert analysis.pack_id == pack_id


def test_latest_analysis_treats_null_pack_as_default(db: Session) -> None:
    """Latest analysis with pack_id NULL is still returned (treated as default pack)."""
    company = Company(name="Null Pack Co", website_url="https://nullpack.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    record = AnalysisRecord(
        company_id=company.id,
        source_type="full_analysis",
        stage="scaling_team",
        pack_id=None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Query latest analysis (as views do) - should return record with pack_id NULL
    latest = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.company_id == company.id)
        .order_by(AnalysisRecord.created_at.desc())
        .first()
    )
    assert latest is not None
    assert latest.pack_id is None
    assert latest.stage == "scaling_team"
