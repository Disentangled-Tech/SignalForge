"""Integration test: ingestion → scoring pipeline (Issue #96).

Verifies that a synthetic event set produces expected readiness scores
and snapshots are persisted correctly. Uses TestAdapter with frozen date
for determinism.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models import (
    Company,
    EngagementSnapshot,
    ReadinessSnapshot,
    SignalEvent,
    SignalInstance,
)
from app.pipeline.deriver_engine import run_deriver
from app.services.ingestion.ingest_daily import run_ingest_daily
from app.services.readiness.score_nightly import run_score_nightly

# Test domains used by TestAdapter
_TEST_DOMAINS = ("testa.example.com", "testb.example.com", "testc.example.com")

# Fixed date matching TestAdapter event times (2026-02-18) for deterministic scoring
_AS_OF = date(2026, 2, 18)


@pytest.fixture(autouse=True)
def _cleanup_test_adapter_data(db: Session) -> None:
    """Remove test adapter data before each test (handles pre-existing data from prior runs)."""
    company_ids = [
        row[0]
        for row in db.query(Company.id)
        .filter(Company.domain.in_(_TEST_DOMAINS))
        .all()
    ]
    if company_ids:
        db.query(SignalInstance).filter(
            SignalInstance.entity_id.in_(company_ids)
        ).delete(synchronize_session="fetch")
        db.query(EngagementSnapshot).filter(
            EngagementSnapshot.company_id.in_(company_ids)
        ).delete(synchronize_session="fetch")
        db.query(ReadinessSnapshot).filter(
            ReadinessSnapshot.company_id.in_(company_ids)
        ).delete(synchronize_session="fetch")
    db.query(SignalEvent).filter(SignalEvent.source == "test").delete(
        synchronize_session="fetch"
    )
    db.query(Company).filter(Company.domain.in_(_TEST_DOMAINS)).delete(
        synchronize_session="fetch"
    )
    db.commit()


def test_ingestion_to_scoring_pipeline_produces_expected_snapshot(
    db: Session,
) -> None:
    """End-to-end: ingest → score produces ReadinessSnapshot with valid dimensions.

    - Synthetic events from TestAdapter (funding_raised, job_posted_engineering,
      cto_role_posted) at 2026-02-18
    - Freeze date.today() to 2026-02-18 for deterministic scoring
    - Assert snapshot exists, dimensions in valid range, explain populated
    """
    with patch("app.services.readiness.score_nightly.date") as mock_date:
        mock_date.today.return_value = _AS_OF

        # 1. Run ingestion (TestAdapter returns 3 events)
        ingest_result = run_ingest_daily(db)
        assert ingest_result["status"] == "completed"
        assert ingest_result["inserted"] == 3

        events = db.query(SignalEvent).filter(SignalEvent.source == "test").all()
        assert len(events) == 3
        assert all(e.company_id is not None for e in events)

        companies = (
            db.query(Company)
            .filter(Company.domain.in_(_TEST_DOMAINS))
            .all()
        )
        assert len(companies) == 3

        # 2. Run scoring
        score_result = run_score_nightly(db)
        assert score_result["status"] == "completed"
        assert score_result["companies_scored"] >= 1

        # 3. Assert snapshots persisted correctly
        snapshots = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id.in_(c.id for c in companies),
                ReadinessSnapshot.as_of == _AS_OF,
            )
            .all()
        )
        assert len(snapshots) >= 1

        for snapshot in snapshots:
            # Dimensions in valid range (0-100)
            assert 0 <= snapshot.momentum <= 100
            assert 0 <= snapshot.complexity <= 100
            assert 0 <= snapshot.pressure <= 100
            assert 0 <= snapshot.leadership_gap <= 100
            assert 0 <= snapshot.composite <= 100

            # Explain payload populated (v2-spec §4.5)
            assert snapshot.explain is not None
            explain = snapshot.explain
            assert "weights" in explain or "dimensions" in explain or "top_events" in explain


def test_ingest_then_derive_then_score(
    db: Session,
    fractional_cto_pack_id,
) -> None:
    """End-to-end: ingest → derive → score. Deriver populates signal_instances."""

    with patch("app.services.readiness.score_nightly.date") as mock_date:
        mock_date.today.return_value = _AS_OF

        # 1. Run ingestion (TestAdapter returns 3 events)
        ingest_result = run_ingest_daily(db)
        assert ingest_result["status"] == "completed"
        assert ingest_result["inserted"] == 3

        events = db.query(SignalEvent).filter(SignalEvent.source == "test").all()
        assert len(events) == 3
        assert all(e.company_id is not None for e in events)

        companies = (
            db.query(Company)
            .filter(Company.domain.in_(_TEST_DOMAINS))
            .all()
        )
        assert len(companies) == 3

        # 2. Run derive (populates signal_instances from SignalEvents)
        derive_result = run_deriver(
            db, pack_id=fractional_cto_pack_id, company_ids=[c.id for c in companies]
        )
        assert derive_result["status"] == "completed"
        assert derive_result["instances_upserted"] == 3
        assert derive_result["events_processed"] == 3

        instances = (
            db.query(SignalInstance)
            .filter(SignalInstance.entity_id.in_(c.id for c in companies))
            .filter(SignalInstance.pack_id == fractional_cto_pack_id)
            .all()
        )
        assert len(instances) == 3

        # 3. Run scoring (uses SignalEvents; produces snapshots)
        score_result = run_score_nightly(db, pack_id=fractional_cto_pack_id)
        assert score_result["status"] == "completed"
        assert score_result["companies_scored"] >= 1

        snapshots = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id.in_(c.id for c in companies),
                ReadinessSnapshot.as_of == _AS_OF,
                ReadinessSnapshot.pack_id == fractional_cto_pack_id,
            )
            .all()
        )
        assert len(snapshots) >= 1
