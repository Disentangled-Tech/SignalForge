"""Tests for daily aggregation job (Issue #246, Phase 4)."""

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
from app.services.aggregation.daily_aggregation import run_daily_aggregation

# Test domains used by TestAdapter (same as test_ingestion_scoring_integration)
_TEST_DOMAINS = ("testa.example.com", "testb.example.com", "testc.example.com")

# Fixed date matching TestAdapter event times (2026-02-18) for deterministic scoring
_AS_OF = date(2026, 2, 18)


@pytest.fixture(autouse=True)
def _cleanup_test_adapter_data(db: Session) -> None:
    """Remove test adapter data before each test."""
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


def test_daily_aggregation_full_run_with_test_adapter_asserts_ranked_output(
    db: Session,
    fractional_cto_pack_id,
) -> None:
    """Integration: full run with TestAdapter, assert ranked output visible.

    - TestAdapter returns 3 events (funding_raised, job_posted_engineering, cto_role_posted)
    - run_daily_aggregation runs ingest → derive → score
    - Assert status completed, ranked_companies non-empty, each item has name/composite/band
    """
    with (
        patch("app.services.readiness.score_nightly.date") as mock_date,
        patch("app.services.aggregation.daily_aggregation.date") as mock_date_da,
    ):
        mock_date.today.return_value = _AS_OF
        mock_date_da.today.return_value = _AS_OF

        result = run_daily_aggregation(db, pack_id=fractional_cto_pack_id)

    assert result["status"] == "completed"
    assert result["ingest_result"]["status"] == "completed"
    assert result["ingest_result"]["inserted"] == 3
    assert result["derive_result"]["status"] == "completed"
    assert result["score_result"]["status"] == "completed"
    assert result["score_result"]["companies_scored"] >= 1

    ranked = result["ranked_companies"]
    assert result["ranked_count"] == len(ranked)
    assert len(ranked) >= 1, "Ranked output should be visible after full run"

    for item in ranked:
        assert "name" in item
        assert "composite" in item
        assert "band" in item
        assert isinstance(item["name"], str)
        assert isinstance(item["composite"], (int, float))
        assert 0 <= item["composite"] <= 100
