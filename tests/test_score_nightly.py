"""Tests for nightly TRS scoring job (Issue #104)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models import Company, EngagementSnapshot, JobRun, ReadinessSnapshot, SignalEvent, SignalPack, Watchlist
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

    @pytest.mark.integration
    def test_nightly_score_creates_snapshots_with_pack_id(self, db: Session) -> None:
        """Nightly score creates ReadinessSnapshot and EngagementSnapshot with pack_id (Issue #189)."""
        pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
        if pack is None:
            pytest.skip("fractional_cto_v1 pack not found (run migration 20260223_signal_packs)")

        company = Company(name="PackCo", website_url="https://pack.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        db.add(
            SignalEvent(
                company_id=company.id,
                source="test",
                event_type="funding_raised",
                event_time=_days_ago(5),
                confidence=0.9,
            )
        )
        db.commit()

        result = run_score_nightly(db)

        assert result["status"] == "completed"
        assert result["companies_scored"] >= 1

        rs = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id == company.id,
                ReadinessSnapshot.as_of == date.today(),
            )
            .first()
        )
        assert rs is not None
        assert rs.pack_id == pack.id

        es = (
            db.query(EngagementSnapshot)
            .filter(
                EngagementSnapshot.company_id == company.id,
                EngagementSnapshot.as_of == date.today(),
            )
            .first()
        )
        assert es is not None
        assert es.pack_id == pack.id

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

    def test_re_run_same_day_does_not_duplicate(self, db: Session) -> None:
        """Re-running same day upserts; no duplicate rows (Issue #91 AC)."""
        company = Company(
            name="IdempotentCo",
            website_url="https://idempotent.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        db.add(
            SignalEvent(
                company_id=company.id,
                source="test",
                event_type="funding_raised",
                event_time=_days_ago(5),
                confidence=0.9,
            )
        )
        db.commit()

        run_score_nightly(db)
        count_before = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id == company.id,
                ReadinessSnapshot.as_of == date.today(),
            )
            .count()
        )
        assert count_before == 1

        run_score_nightly(db)
        count_after = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id == company.id,
                ReadinessSnapshot.as_of == date.today(),
            )
            .count()
        )
        assert count_after == count_before

    def test_scores_match_golden_values(self, db: Session) -> None:
        """Snapshot dimensions match expected values from engine (Issue #91, v2-spec §11)."""
        company = Company(
            name="GoldenCo",
            website_url="https://golden.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        # funding_raised 5d ago (conf 0.9) -> M ~31-32; cto_role_posted 50d ago -> G=70
        db.add_all([
            SignalEvent(
                company_id=company.id,
                source="test",
                event_type="funding_raised",
                event_time=_days_ago(5),
                confidence=0.9,
            ),
            SignalEvent(
                company_id=company.id,
                source="test",
                event_type="cto_role_posted",
                event_time=_days_ago(50),
                confidence=0.7,
            ),
        ])
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
        # funding_raised: 35*1.0*0.9=31.5 -> 31 or 32
        assert snapshot.momentum in (31, 32)
        # cto_role_posted without cto_hired -> G=70 (test_no_cto_hired_yields_full_gap)
        assert snapshot.leadership_gap == 70
        # R = 0.30*M + 0.30*C + 0.25*P + 0.15*G; funding adds to P too
        assert snapshot.composite >= 20
        assert snapshot.composite <= 35

    def test_nightly_creates_engagement_snapshots(self, db: Session) -> None:
        """Nightly job creates both ReadinessSnapshot and EngagementSnapshot (Issue #107)."""
        company = Company(
            name="ESLIntegrationCo",
            website_url="https://esl-integration.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        db.add(
            SignalEvent(
                company_id=company.id,
                source="test",
                event_type="funding_raised",
                event_time=_days_ago(5),
                confidence=0.9,
            )
        )
        db.commit()

        result = run_score_nightly(db)

        assert result["status"] == "completed"
        assert result["companies_scored"] >= 1
        assert result["companies_engagement"] >= 1

        readiness = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id == company.id,
                ReadinessSnapshot.as_of == date.today(),
            )
            .first()
        )
        assert readiness is not None

        engagement = (
            db.query(EngagementSnapshot)
            .filter(
                EngagementSnapshot.company_id == company.id,
                EngagementSnapshot.as_of == date.today(),
            )
            .first()
        )
        assert engagement is not None
        assert engagement.outreach_score == round(
            readiness.composite * engagement.esl_score
        )

    def test_no_engagement_snapshot_when_trs_missing(self, db: Session) -> None:
        """When TRS is missing (no events), no EngagementSnapshot is created (Issue #107)."""
        company = Company(
            name="NoTRSCo",
            website_url="https://no-trs.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        db.add(Watchlist(company_id=company.id, is_active=True))
        db.commit()

        result = run_score_nightly(db)

        assert result["status"] == "completed"
        engagement = (
            db.query(EngagementSnapshot)
            .filter(
                EngagementSnapshot.company_id == company.id,
                EngagementSnapshot.as_of == date.today(),
            )
            .first()
        )
        assert engagement is None

    def test_re_run_same_day_does_not_duplicate_engagement(self, db: Session) -> None:
        """Re-running nightly upserts EngagementSnapshot; no duplicate rows (Issue #107)."""
        company = Company(
            name="EngagementIdempotentCo",
            website_url="https://engagement-idempotent.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        db.add(
            SignalEvent(
                company_id=company.id,
                source="test",
                event_type="funding_raised",
                event_time=_days_ago(5),
                confidence=0.9,
            )
        )
        db.commit()

        run_score_nightly(db)
        count_before = (
            db.query(EngagementSnapshot)
            .filter(
                EngagementSnapshot.company_id == company.id,
                EngagementSnapshot.as_of == date.today(),
            )
            .count()
        )
        assert count_before == 1

        run_score_nightly(db)
        count_after = (
            db.query(EngagementSnapshot)
            .filter(
                EngagementSnapshot.company_id == company.id,
                EngagementSnapshot.as_of == date.today(),
            )
            .count()
        )
        assert count_after == count_before
