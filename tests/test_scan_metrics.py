"""Tests for scan metrics service (issue #61)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.job_run import JobRun
from app.services.scan_metrics import get_scan_change_rate_30d


def _job(
    job_type: str,
    started_at: datetime,
    companies_processed: int | None = None,
    companies_analysis_changed: int | None = None,
) -> JobRun:
    j = JobRun(job_type=job_type, status="completed", started_at=started_at)
    j.companies_processed = companies_processed
    j.companies_analysis_changed = companies_analysis_changed
    return j


class TestGetScanChangeRate30d:
    def _clear_job_runs(self, db):
        """Remove all job runs so tests start with a clean slate."""
        db.query(JobRun).delete()
        db.commit()

    def test_no_jobs_returns_none_zero_zero(self, db):
        self._clear_job_runs(db)
        """No scan jobs in last 30 days → (None, 0, 0)."""
        pct, changed, processed = get_scan_change_rate_30d(db)
        assert pct is None
        assert changed == 0
        assert processed == 0

    def test_one_job_returns_correct_rate(self, db):
        """One scan job 10/50 → (20.0, 10, 50)."""
        self._clear_job_runs(db)
        now = datetime.now(UTC)
        job = _job("scan", now, companies_processed=50, companies_analysis_changed=10)
        db.add(job)
        db.commit()

        pct, changed, processed = get_scan_change_rate_30d(db)
        assert pct == 20.0
        assert changed == 10
        assert processed == 50

    def test_multiple_jobs_aggregates(self, db):
        """Multiple scan jobs → correct aggregation."""
        self._clear_job_runs(db)
        now = datetime.now(UTC)
        db.add(_job("scan", now, companies_processed=20, companies_analysis_changed=5))
        db.add(_job("scan", now, companies_processed=30, companies_analysis_changed=10))
        db.commit()

        pct, changed, processed = get_scan_change_rate_30d(db)
        assert pct == 30.0  # 15/50 = 30%
        assert changed == 15
        assert processed == 50

    def test_excludes_old_jobs(self, db):
        """Jobs older than 30 days are excluded."""
        self._clear_job_runs(db)
        now = datetime.now(UTC)
        old = now - timedelta(days=35)
        db.add(_job("scan", old, companies_processed=100, companies_analysis_changed=50))
        db.add(_job("scan", now, companies_processed=10, companies_analysis_changed=2))
        db.commit()

        pct, changed, processed = get_scan_change_rate_30d(db)
        assert pct == 20.0  # 2/10 only
        assert changed == 2
        assert processed == 10

    def test_excludes_non_scan_jobs(self, db):
        """Only job_type='scan' counts; briefing/company_scan excluded."""
        self._clear_job_runs(db)
        now = datetime.now(UTC)
        db.add(_job("scan", now, companies_processed=10, companies_analysis_changed=3))
        db.add(
            _job(
                "briefing",
                now,
                companies_processed=5,
                companies_analysis_changed=1,
            )
        )
        db.commit()

        pct, changed, processed = get_scan_change_rate_30d(db)
        assert pct == 30.0  # 3/10 from scan only
        assert changed == 3
        assert processed == 10

    def test_null_changed_treated_as_zero(self, db):
        """Legacy JobRuns with NULL companies_analysis_changed → 0."""
        self._clear_job_runs(db)
        now = datetime.now(UTC)
        db.add(_job("scan", now, companies_processed=10, companies_analysis_changed=None))
        db.commit()

        pct, changed, processed = get_scan_change_rate_30d(db)
        assert pct == 0.0
        assert changed == 0
        assert processed == 10
