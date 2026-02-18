"""Tests for nightly TRS scoring job (Issue #104)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models import Company, JobRun, ReadinessSnapshot, SignalEvent, Watchlist
from app.services.readiness.score_nightly import run_score_nightly
from app.services.readiness.snapshot_writer import write_readiness_snapshot as real_write


def _days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


class TestRunScoreNightly:
    """Nightly scoring job."""

    def test_scores_companies_with_events(self, db: Session) -> None:
        """Companies with SignalEvents get snapshots."""
        company = Company(name="EventsCo", website_url="https://events.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        ev = SignalEvent(
            company_id=company.id,
            source="test",
            event_type="funding_raised",
            event_time=_days_ago(5),
            confidence=0.9,
        )
        db.add(ev)
        db.commit()

        result = run_score_nightly(db)

        assert result["status"] == "completed"
        assert result["companies_scored"] >= 1
        snapshot = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id == company.id,
                ReadinessSnapshot.as_of == date.today(),
            )
            .first()
        )
        assert snapshot is not None
        assert snapshot.composite >= 0
        assert snapshot.explain is not None

    def test_includes_watchlist_companies(self, db: Session) -> None:
        """Watchlist companies are attempted (may skip if no events)."""
        company = Company(name="WatchlistCo", website_url="https://watchlist.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        db.add(Watchlist(company_id=company.id, is_active=True))
        db.commit()

        # No SignalEvents - write_readiness_snapshot returns None
        result = run_score_nightly(db)

        assert result["status"] == "completed"
        # Company was in the set to score; snapshot is None (no events)
        assert result["companies_skipped"] >= 1 or result["companies_scored"] >= 1

    def test_watchlist_company_with_events_gets_snapshot(self, db: Session) -> None:
        """Watchlist company with events gets snapshot."""
        company = Company(name="WatchlistEventsCo", website_url="https://we.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        db.add(Watchlist(company_id=company.id, is_active=True))
        db.add(
            SignalEvent(
                company_id=company.id,
                source="test",
                event_type="funding_raised",
                event_time=_days_ago(3),
                confidence=0.9,
            )
        )
        db.commit()

        result = run_score_nightly(db)

        assert result["status"] == "completed"
        assert result["companies_scored"] >= 1
        snapshot = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id == company.id,
                ReadinessSnapshot.as_of == date.today(),
            )
            .first()
        )
        assert snapshot is not None

    def test_one_failure_does_not_stop_run(self, db: Session) -> None:
        """One company failure does not stop the run."""
        c1 = Company(name="GoodCo", website_url="https://good.example.com")
        c2 = Company(name="BadCo", website_url="https://bad.example.com")
        db.add_all([c1, c2])
        db.commit()
        db.refresh(c1)
        db.refresh(c2)

        db.add(
            SignalEvent(
                company_id=c1.id,
                source="test",
                event_type="funding_raised",
                event_time=_days_ago(5),
                confidence=0.9,
            )
        )
        db.add(
            SignalEvent(
                company_id=c2.id,
                source="test",
                event_type="funding_raised",
                event_time=_days_ago(5),
                confidence=0.9,
            )
        )
        db.commit()

        call_count = 0

        def mock_write(inner_db, company_id, as_of, company_status=None):
            nonlocal call_count
            call_count += 1
            if company_id == c2.id:
                raise RuntimeError("Simulated failure")
            return real_write(inner_db, company_id, as_of, company_status)

        with patch(
            "app.services.readiness.score_nightly.write_readiness_snapshot",
            side_effect=mock_write,
        ):
            result = run_score_nightly(db)

        assert result["status"] == "completed"
        assert result["companies_scored"] >= 1
        assert result["error"] is not None
        assert "Simulated failure" in result["error"]
        # c1 should have snapshot
        snap1 = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id == c1.id,
                ReadinessSnapshot.as_of == date.today(),
            )
            .first()
        )
        assert snap1 is not None

    def test_creates_job_run(self, db: Session) -> None:
        """JobRun record is created with job_type=score."""
        result = run_score_nightly(db)

        job = db.query(JobRun).filter(JobRun.job_type == "score").order_by(JobRun.id.desc()).first()
        assert job is not None
        assert job.status == "completed"
        assert job.finished_at is not None
        assert result["job_run_id"] == job.id
