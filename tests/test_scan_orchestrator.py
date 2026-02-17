"""Tests for scan orchestrator service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.company import Company
from app.models.job_run import JobRun
from app.models.signal_record import SignalRecord
from app.models.analysis_record import AnalysisRecord
from app.services.scan_orchestrator import _analysis_changed, infer_source_type


# ── Helpers ──────────────────────────────────────────────────────────


def _company(id: int, name: str, website_url: str | None = "https://example.com") -> MagicMock:
    c = MagicMock(spec=Company)
    c.id = id
    c.name = name
    c.website_url = website_url
    c.last_scan_at = None
    return c


def _mock_db(*companies: Company):
    """Return a mock Session pre-loaded with company list."""
    db = MagicMock()
    db.query.return_value.all.return_value = list(companies)

    def _query_filter(model):
        chain = MagicMock()
        if model is Company:
            def _filter_first(*a, **kw):
                inner = MagicMock()
                inner.first.return_value = companies[0] if companies else None
                return inner
            chain.filter = _filter_first
        return chain

    db.query.side_effect = lambda m: (
        _query_filter(m) if m is Company else db.query.return_value
    )
    return db


# ── infer_source_type tests ──────────────────────────────────────────


class TestInferSourceType:
    @pytest.mark.parametrize(
        "url, expected",
        [
            ("https://acme.com", "homepage"),
            ("https://acme.com/", "homepage"),
            ("https://acme.com/blog/post-1", "blog"),
            ("https://acme.com/articles/hello", "blog"),
            ("https://acme.com/jobs", "jobs"),
            ("https://acme.com/careers", "careers"),
            ("https://acme.com/news/latest", "news"),
            ("https://acme.com/press/release", "news"),
            ("https://acme.com/about", "about"),
            ("https://acme.com/about-us", "about"),
            ("https://acme.com/team", "about"),
            ("https://acme.com/products/widget", "homepage"),  # no match → homepage
        ],
    )
    def test_infer(self, url: str, expected: str):
        assert infer_source_type(url) == expected


# ── _analysis_changed tests (issue #61) ───────────────────────────────


def _analysis(stage: str, pain_signals: dict | None = None) -> MagicMock:
    """Create a mock AnalysisRecord with stage and pain_signals_json."""
    r = MagicMock(spec=AnalysisRecord)
    r.stage = stage
    r.pain_signals_json = pain_signals or {}
    return r


class TestAnalysisChanged:
    def test_prev_none_returns_false(self):
        """No prior analysis → not changed."""
        new = _analysis("early_customers", {"signals": {"hiring_engineers": {"value": True}}})
        assert _analysis_changed(None, new) is False

    def test_stage_differs_returns_true(self):
        """Stage change → changed."""
        prev = _analysis("early_customers")
        new = _analysis("scaling_team")
        assert _analysis_changed(prev, new) is True

    def test_stage_case_insensitive_no_change(self):
        """Stage same (case diff) → not changed."""
        prev = _analysis("Early_Customers")
        new = _analysis("early_customers")
        assert _analysis_changed(prev, new) is False

    def test_pain_signal_differs_returns_true(self):
        """Pain signal value change → changed."""
        prev = _analysis("early_customers", {"signals": {"hiring_engineers": {"value": False}}})
        new = _analysis("early_customers", {"signals": {"hiring_engineers": {"value": True}}})
        assert _analysis_changed(prev, new) is True

    def test_identical_returns_false(self):
        """Same stage and signals → not changed."""
        prev = _analysis("early_customers", {"signals": {"hiring_engineers": {"value": True}}})
        new = _analysis("early_customers", {"signals": {"hiring_engineers": {"value": True}}})
        assert _analysis_changed(prev, new) is False


# ── run_scan_company_full tests ───────────────────────────────────────


class TestRunScanCompanyFull:
    @pytest.mark.asyncio
    @patch("app.services.scan_orchestrator.score_company")
    @patch("app.services.scan_orchestrator.analyze_company")
    @patch("app.services.scan_orchestrator.run_scan_company", new_callable=AsyncMock)
    async def test_runs_scan_analysis_scoring(self, mock_scan, mock_analyze, mock_score):
        """run_scan_company_full runs scan, analysis, and scoring; updates company score."""
        from app.services.scan_orchestrator import run_scan_company_full

        db = MagicMock()
        # No prior analysis (for change detection)
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            None
        )
        mock_scan.return_value = 2
        analysis = MagicMock()
        mock_analyze.return_value = analysis

        new_count, result_analysis, changed = await run_scan_company_full(db, 1)

        assert new_count == 2
        assert result_analysis is analysis
        assert changed is False  # no prev analysis
        mock_scan.assert_awaited_once_with(db, 1)
        mock_analyze.assert_called_once_with(db, 1)
        mock_score.assert_called_once_with(db, 1, analysis)


# ── run_scan_company tests ───────────────────────────────────────────


class TestRunScanCompany:
    @pytest.mark.asyncio
    @patch("app.services.scan_orchestrator.store_signal")
    @patch("app.services.scan_orchestrator.discover_pages", new_callable=AsyncMock)
    async def test_returns_new_signal_count(self, mock_discover, mock_store):
        """run_scan_company returns count of non-duplicate signals."""
        from app.services.scan_orchestrator import run_scan_company

        company = _company(1, "Acme")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = company

        mock_discover.return_value = [
            ("https://acme.com/", "Homepage text"),
            ("https://acme.com/blog/post", "Blog text"),
        ]
        # First is new, second is duplicate (None)
        mock_store.side_effect = [MagicMock(), None]

        count = await run_scan_company(db, 1)
        assert count == 1
        assert mock_store.call_count == 2

    @pytest.mark.asyncio
    @patch("app.services.scan_orchestrator.discover_pages", new_callable=AsyncMock)
    async def test_no_website_returns_zero(self, mock_discover):
        from app.services.scan_orchestrator import run_scan_company

        company = _company(2, "NoSite", website_url=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = company

        count = await run_scan_company(db, 2)
        assert count == 0
        mock_discover.assert_not_called()


# ── run_scan_all tests ───────────────────────────────────────────────


class TestRunScanAll:
    @pytest.mark.asyncio
    @patch("app.services.scan_orchestrator.run_scan_company_full", new_callable=AsyncMock)
    async def test_creates_job_run_and_completes(self, mock_scan_full):
        """run_scan_all runs full pipeline (scan+analysis+scoring) per company."""
        from app.services.scan_orchestrator import run_scan_all

        c1 = _company(1, "Alpha")
        c2 = _company(2, "Beta")
        db = MagicMock()
        db.query.return_value.all.return_value = [c1, c2]
        mock_scan_full.return_value = (3, MagicMock(), False)  # (new_signals, analysis, changed)

        job = await run_scan_all(db)

        assert isinstance(job, JobRun)
        assert job.status == "completed"
        assert job.companies_processed == 2
        assert job.companies_analysis_changed == 0
        assert job.finished_at is not None
        assert job.error_message is None
        assert mock_scan_full.await_count == 2

    @pytest.mark.asyncio
    @patch("app.services.scan_orchestrator.run_scan_company_full", new_callable=AsyncMock)
    async def test_error_isolation(self, mock_scan_full):
        """One company failure must NOT stop the others."""
        from app.services.scan_orchestrator import run_scan_all

        c1 = _company(1, "Good")
        c2 = _company(2, "Bad")
        c3 = _company(3, "AlsoGood")
        db = MagicMock()
        db.query.return_value.all.return_value = [c1, c2, c3]

        mock_scan_full.side_effect = [
            (2, MagicMock(), False),
            RuntimeError("network down"),
            (1, MagicMock(), True),
        ]

        job = await run_scan_all(db)

        # Despite one error the job should complete
        assert job.status == "completed"
        assert job.companies_processed == 2  # c1 + c3
        assert job.companies_analysis_changed == 1  # c3 had changed=True
        assert "Company 2" in job.error_message
        assert "network down" in job.error_message

    @pytest.mark.asyncio
    @patch("app.services.scan_orchestrator.run_scan_company_full", new_callable=AsyncMock)
    async def test_all_failed_status(self, mock_scan_full):
        """If every company with a URL fails, job status should be 'failed'."""
        from app.services.scan_orchestrator import run_scan_all

        c1 = _company(1, "Bad1")
        c2 = _company(2, "Bad2")
        db = MagicMock()
        db.query.return_value.all.return_value = [c1, c2]

        mock_scan_full.side_effect = RuntimeError("boom")

        job = await run_scan_all(db)

        assert job.status == "failed"
        assert job.companies_processed == 0
        assert job.error_message is not None


# ── run_scan_company_with_job tests ───────────────────────────────────


class TestRunScanCompanyWithJob:
    @pytest.mark.asyncio
    @patch("app.services.scan_orchestrator.score_company")
    @patch("app.services.scan_orchestrator.analyze_company")
    @patch("app.services.scan_orchestrator.run_scan_company", new_callable=AsyncMock)
    async def test_creates_job_run_and_completes(
        self, mock_scan, mock_analyze, mock_score
    ):
        """run_scan_company_with_job creates JobRun and completes successfully."""
        from app.services.scan_orchestrator import run_scan_company_with_job

        db = MagicMock()
        mock_scan.return_value = 2
        mock_analyze.return_value = MagicMock()

        job = await run_scan_company_with_job(db, 1)

        assert job.job_type == "company_scan"
        assert job.company_id == 1
        assert job.status == "completed"
        assert job.finished_at is not None
        db.add.assert_called_once()
        mock_scan.assert_awaited_once_with(db, 1)
        mock_analyze.assert_called_once_with(db, 1)
        mock_score.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.scan_orchestrator.run_scan_company", new_callable=AsyncMock)
    async def test_scan_failure_marks_job_failed(self, mock_scan):
        """When run_scan_company raises, job status is failed with error_message."""
        from app.services.scan_orchestrator import run_scan_company_with_job

        db = MagicMock()
        mock_scan.side_effect = RuntimeError("network error")

        job = await run_scan_company_with_job(db, 1)

        assert job.status == "failed"
        assert "network error" in (job.error_message or "")
        assert job.finished_at is not None

    @pytest.mark.asyncio
    @patch("app.services.scan_orchestrator.score_company")
    @patch("app.services.scan_orchestrator.analyze_company")
    @patch("app.services.scan_orchestrator.run_scan_company", new_callable=AsyncMock)
    async def test_updates_existing_job_when_job_id_provided(
        self, mock_scan, mock_analyze, mock_score
    ):
        """When job_id is provided, updates that JobRun instead of creating new one."""
        from app.services.scan_orchestrator import run_scan_company_with_job

        db = MagicMock()
        existing_job = MagicMock(spec=JobRun)
        existing_job.id = 42
        existing_job.status = "running"
        existing_job.finished_at = None
        existing_job.error_message = None
        db.query.return_value.filter.return_value.first.return_value = existing_job

        mock_scan.return_value = 1
        mock_analyze.return_value = MagicMock()

        job = await run_scan_company_with_job(db, 1, job_id=42)

        assert job.id == 42
        assert job.status == "completed"
        db.add.assert_not_called()
        db.query.return_value.filter.assert_called()
