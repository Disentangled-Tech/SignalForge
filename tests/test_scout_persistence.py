"""Integration tests: scout run + evidence bundle persistence; no companies/signal_events writes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from app.models.signal_event import SignalEvent


@pytest.mark.integration
def test_insert_scout_run_and_bundle_read_back(
    db: Session,
) -> None:
    """Insert scout run + evidence bundle, read back; no new companies or signal_events."""
    companies_before = db.query(Company).count()
    events_before = db.query(SignalEvent).count()

    run_id = uuid4()
    run_row = ScoutRun(
        run_id=run_id,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        model_version="test-model",
        tokens_used=100,
        latency_ms=500,
        page_fetch_count=0,
        config_snapshot={"icp": "test"},
        status="completed",
        error_message=None,
    )
    db.add(run_row)
    db.flush()

    bundle_row = ScoutEvidenceBundle(
        scout_run_id=run_row.id,
        candidate_company_name="TestCo",
        company_website="https://test.example.com",
        why_now_hypothesis="Testing.",
        evidence=[{"url": "https://test.example.com", "quoted_snippet": "Test.", "timestamp_seen": "2026-02-27T12:00:00Z", "source_type": "test", "confidence_score": 0.8}],
        missing_information=[],
        raw_llm_output=None,
    )
    db.add(bundle_row)
    db.commit()

    # Read back
    run_read = db.query(ScoutRun).filter(ScoutRun.run_id == run_id).first()
    assert run_read is not None
    assert run_read.model_version == "test-model"
    assert run_read.status == "completed"

    bundles_read = db.query(ScoutEvidenceBundle).filter(
        ScoutEvidenceBundle.scout_run_id == run_read.id
    ).all()
    assert len(bundles_read) == 1
    assert bundles_read[0].candidate_company_name == "TestCo"
    assert len(bundles_read[0].evidence) == 1

    # No new domain rows
    assert db.query(Company).count() == companies_before
    assert db.query(SignalEvent).count() == events_before
