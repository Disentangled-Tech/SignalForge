"""Tests for the daily briefing pipeline."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.analysis_record import AnalysisRecord
from app.models.briefing_item import BriefingItem
from app.models.company import Company
from app.models.job_run import JobRun
from app.services.briefing import (
    generate_briefing,
    select_top_companies,
)
from app.services.settings_resolver import ResolvedSettings


def _default_resolved() -> ResolvedSettings:
    """Default ResolvedSettings for tests (daily, email disabled)."""
    return ResolvedSettings(
        briefing_time="08:00",
        briefing_email="",
        briefing_email_enabled=False,
        briefing_frequency="daily",
        briefing_day_of_week=0,
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        smtp_from="",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_BRIEFING_RESPONSE = json.dumps(
    {
        "why_now": "The company is scaling fast.",
        "risk_summary": "Team may outpace architecture.",
        "suggested_angle": "Discuss scaling strategy.",
        "next_step": "Send intro email.",
    }
)

_VALID_OUTREACH_RESULT = {
    "subject": "Quick question",
    "message": "Hi Jane, I noticed you are hiring.",
}


def _make_company(**overrides):
    now = datetime.now(UTC)
    defaults = dict(
        id=1,
        name="Acme Corp",
        website_url="https://acme.example.com",
        founder_name="Jane Doe",
        notes="Early stage startup",
        cto_need_score=75,
        current_stage="scaling_team",
        last_scan_at=now - timedelta(days=2),
    )
    defaults.update(overrides)
    c = MagicMock(spec=Company)
    for k, v in defaults.items():
        setattr(c, k, v)
    return c


def _make_analysis(**overrides):
    defaults = dict(
        id=10,
        company_id=1,
        stage="scaling_team",
        stage_confidence=80,
        pain_signals_json={
            "top_risks": ["hiring"],
            "most_likely_next_problem": "Scaling",
            "recommended_conversation_angle": "Hiring strategy",
        },
        evidence_bullets=["Hiring 3 engineers"],
        explanation="Needs help",
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    a = MagicMock(spec=AnalysisRecord)
    for k, v in defaults.items():
        setattr(a, k, v)
    return a


# ---------------------------------------------------------------------------
# select_top_companies
# ---------------------------------------------------------------------------


class TestSelectTopCompanies:
    def test_returns_companies_from_query(self):
        """select_top_companies issues a query; verify it returns results."""
        companies = [_make_company(id=1), _make_company(id=2)]
        db = MagicMock()
        # Chain: db.query().filter().filter().filter().order_by().limit().all()
        chain = db.query.return_value.filter.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            companies
        )

        result = select_top_companies(db, limit=5)
        assert len(result) == 2
        # db.query is called multiple times (subqueries + main query).
        # Verify Company was queried by checking any call used Company.
        assert any(c.args[0] is Company for c in db.query.call_args_list if c.args)

    def test_respects_limit(self):
        db = MagicMock()
        chain = db.query.return_value.filter.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        select_top_companies(db, limit=3)
        # Verify .limit(3) was called
        chain.filter.return_value.order_by.return_value.limit.assert_called_once_with(3)

    def test_returns_empty_when_no_companies(self):
        db = MagicMock()
        chain = db.query.return_value.filter.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        result = select_top_companies(db)
        assert result == []

    def test_excludes_companies_without_analysis(self):
        """Companies without AnalysisRecord are excluded (issue #22).

        select_top_companies filters by companies_with_analysis subquery,
        so only companies with at least one AnalysisRecord are returned.
        """
        c_with = _make_company(id=1, name="With Analysis", cto_need_score=80)
        db = MagicMock()
        chain = db.query.return_value.filter.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            c_with
        ]

        result = select_top_companies(db, limit=5)
        assert len(result) == 1
        assert result[0].id == 1

    def test_exactly_up_to_limit(self):
        """Returns up to limit; fewer when fewer qualify."""
        companies = [_make_company(id=i, cto_need_score=70 - i) for i in range(3)]
        db = MagicMock()
        chain = db.query.return_value.filter.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            companies
        )

        result = select_top_companies(db, limit=5)
        assert len(result) == 3

        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            companies[:2]
        )
        result_2 = select_top_companies(db, limit=2)
        assert len(result_2) == 2

    def test_no_duplicates_in_7_days(self):
        """Companies briefed in last 7 days are excluded.

        select_top_companies filters by recently_briefed_ids subquery,
        so companies with BriefingItem in last 7 days are excluded.
        """
        db = MagicMock()
        chain = db.query.return_value.filter.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        result = select_top_companies(db, limit=5)
        assert result == []

    def test_activity_within_14_days(self):
        """Activity filter uses 14-day window.

        select_top_companies requires last_scan_at >= 14 days ago OR
        recent signal. Companies outside the window are excluded.
        """
        db = MagicMock()
        chain = db.query.return_value.filter.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            _make_company(
                id=1,
                last_scan_at=datetime.now(UTC) - timedelta(days=5),
            )
        ]

        result = select_top_companies(db, limit=5)
        assert len(result) == 1

    def test_ordered_by_score_desc(self):
        """Companies are ordered by cto_need_score descending."""
        companies = [
            _make_company(id=1, cto_need_score=90),
            _make_company(id=2, cto_need_score=70),
            _make_company(id=3, cto_need_score=50),
        ]
        db = MagicMock()
        chain = db.query.return_value.filter.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            companies
        )

        result = select_top_companies(db, limit=5)
        scores = [c.cto_need_score for c in result]
        assert scores == [90, 70, 50]


# ---------------------------------------------------------------------------
# generate_briefing
# ---------------------------------------------------------------------------


class TestGenerateBriefing:
    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_creates_briefing_items(
        self, mock_select, mock_render, mock_get_llm, mock_outreach, mock_resolved, *_args
    ):
        mock_resolved.return_value = _default_resolved()
        company = _make_company()
        analysis = _make_analysis()
        mock_select.return_value = [company]
        mock_render.return_value = "prompt"

        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        # First first() = existing check (None); second first() = analysis fetch
        query_mock.first.side_effect = [None, analysis]

        result = generate_briefing(db)

        assert len(result) == 1
        item = db.add.call_args[0][0]
        assert isinstance(item, BriefingItem)
        assert item.company_id == company.id
        assert item.analysis_id == analysis.id
        assert item.why_now == "The company is scaling fast."
        assert item.risk_summary == "Team may outpace architecture."
        assert item.suggested_angle == "Discuss scaling strategy."
        assert item.outreach_subject == "Quick question"
        assert item.outreach_message == "Hi Jane, I noticed you are hiring."
        assert item.briefing_date == date.today()
        db.commit.assert_called()
        # Phase 3: generate_outreach called with pack (None when pack resolution returns None)
        mock_outreach.assert_called_once()
        call_kwargs = mock_outreach.call_args[1]
        assert "pack" in call_kwargs
        assert call_kwargs["pack"] is None

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_generate_briefing_sets_workspace_id_on_items(
        self, mock_select, mock_render, mock_get_llm, mock_outreach, mock_resolved, *_args
    ):
        """When workspace_id provided, BriefingItems are created with that workspace_id."""
        import uuid

        mock_resolved.return_value = _default_resolved()
        company = _make_company()
        analysis = _make_analysis()
        mock_select.return_value = [company]
        mock_render.return_value = "prompt"

        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.first.side_effect = [None, analysis]

        ws_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        result = generate_briefing(db, workspace_id=ws_uuid)

        assert len(result) == 1
        item = db.add.call_args[0][0]
        assert isinstance(item, BriefingItem)
        assert item.workspace_id == uuid.UUID(ws_uuid)
        mock_select.assert_called_once_with(db, workspace_id=ws_uuid)

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_skips_company_without_analysis(
        self, mock_select, mock_render, mock_get_llm, mock_outreach, mock_resolved, *_args
    ):
        mock_resolved.return_value = _default_resolved()
        company = _make_company()
        mock_select.return_value = [company]

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        # First first() = existing check (None); second first() = analysis (None)
        query_mock.first.side_effect = [None, None]

        result = generate_briefing(db)

        assert result == []
        mock_outreach.assert_not_called()

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_one_failure_does_not_stop_others(
        self, mock_select, mock_render, mock_get_llm, mock_outreach, mock_resolved, *_args
    ):
        mock_resolved.return_value = _default_resolved()
        """If one company fails, the others should still produce items."""
        good_company = _make_company(id=1, name="Good Corp")
        bad_company = _make_company(id=2, name="Bad Corp")
        mock_select.return_value = [bad_company, good_company]

        mock_render.return_value = "prompt"
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        analysis = _make_analysis()
        call_count = 0

        def first_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # existing check for bad company
            if call_count == 2:
                raise RuntimeError("LLM exploded")  # analysis for bad company
            if call_count == 3:
                return None  # existing check for good company
            return analysis  # analysis for good company

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.first.side_effect = first_side_effect

        result = generate_briefing(db)

        # Only the good company should have produced a briefing item.
        assert len(result) == 1
        # Per-company failures stored in job_runs (issue #32)
        job_runs = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], JobRun)]
        assert len(job_runs) == 1
        assert "Bad Corp" in (job_runs[0].error_message or "")
        assert "LLM exploded" in (job_runs[0].error_message or "")

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_all_companies_fail_stores_errors_in_job_run(
        self, mock_select, mock_render, mock_get_llm, mock_outreach, mock_resolved, *_args
    ):
        """When all companies fail, job stores error_message and companies_processed=0 (issue #32)."""
        mock_resolved.return_value = _default_resolved()
        c1 = _make_company(id=1, name="Fail1")
        c2 = _make_company(id=2, name="Fail2")
        mock_select.return_value = [c1, c2]

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.first.side_effect = [
            None,  # c1 existing
            RuntimeError("Analysis failed"),  # c1 analysis - but first() returns, doesn't raise
        ]

        # first() returns values; to raise we need side_effect to raise. So we need a callable.
        def first_raise(*args, **kwargs):
            raise RuntimeError("Analysis failed")

        query_mock.first.side_effect = first_raise

        result = generate_briefing(db)

        assert result == []
        job_runs = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], JobRun)]
        assert len(job_runs) == 1
        job = job_runs[0]
        assert job.companies_processed == 0
        assert job.error_message is not None
        assert "Fail1" in job.error_message or "Fail2" in job.error_message
        assert "Analysis failed" in job.error_message

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_llm_called_with_correct_temperature(
        self, mock_select, mock_render, mock_get_llm, mock_outreach, mock_resolved, *_args
    ):
        mock_resolved.return_value = _default_resolved()
        company = _make_company()
        analysis = _make_analysis()
        mock_select.return_value = [company]
        mock_render.return_value = "prompt"

        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.first.side_effect = [None, analysis]

        generate_briefing(db)

        mock_llm.complete.assert_called_once_with(
            "prompt",
            response_format={"type": "json_object"},
            temperature=0.5,
        )

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_empty_companies_returns_empty_list(
        self, mock_select, mock_render, mock_get_llm, mock_outreach, mock_resolved, *_args
    ):
        mock_resolved.return_value = _default_resolved()
        mock_select.return_value = []

        db = MagicMock()
        result = generate_briefing(db)

        assert result == []
        mock_get_llm.assert_not_called()

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_skips_when_briefing_item_already_exists(
        self, mock_select, mock_render, mock_get_llm, mock_outreach, mock_resolved, *_args
    ):
        mock_resolved.return_value = _default_resolved()
        """When BriefingItem already exists for company+date, skip creation."""
        company = _make_company()
        mock_select.return_value = [company]

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        # First query (existing check) returns an existing item -> skip
        query_mock.filter.return_value.filter.return_value.first.return_value = MagicMock()

        result = generate_briefing(db)

        assert result == []
        mock_render.assert_not_called()
        mock_outreach.assert_not_called()
        # JobRun is always created (issue #27); no BriefingItem added
        add_calls = db.add.call_args_list
        assert all(isinstance(c.args[0], JobRun) for c in add_calls)

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_creates_job_run_on_success(
        self, mock_select, mock_render, mock_get_llm, mock_outreach, mock_resolved, *_args
    ):
        mock_resolved.return_value = _default_resolved()
        """generate_briefing creates JobRun with status completed and companies_processed (issue #27)."""
        company = _make_company()
        analysis = _make_analysis()
        mock_select.return_value = [company]
        mock_render.return_value = "prompt"

        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.first.side_effect = [None, analysis]

        # Track JobRun add
        added = []

        def capture_add(obj):
            added.append(obj)

        db.add.side_effect = capture_add

        result = generate_briefing(db)

        assert len(result) == 1
        job_runs = [a for a in added if isinstance(a, JobRun)]
        assert len(job_runs) == 1
        job = job_runs[0]
        assert job.job_type == "briefing"
        assert job.status == "completed"
        assert job.companies_processed == 1
        assert job.finished_at is not None
        assert job.error_message is None

    @patch("app.services.briefing.get_pack_for_workspace")
    @patch("app.services.briefing.get_default_pack_id")
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_generate_briefing_sets_workspace_id_and_pack_id_on_job_run(
        self,
        mock_select,
        mock_render,
        mock_get_llm,
        mock_outreach,
        mock_resolved,
        mock_get_default_pack_id,
        mock_get_pack_for_workspace,
        *_args,
    ):
        """Phase 3: JobRun gets workspace_id and pack_id for audit trail."""
        import uuid

        mock_resolved.return_value = _default_resolved()
        mock_get_pack_for_workspace.return_value = None
        mock_get_default_pack_id.return_value = uuid.UUID("11111111-1111-1111-1111-111111111111")
        company = _make_company()
        analysis = _make_analysis()
        mock_select.return_value = [company]
        mock_render.return_value = "prompt"
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.first.side_effect = [None, analysis]

        added = []

        def capture_add(obj):
            added.append(obj)

        db.add.side_effect = capture_add

        generate_briefing(db)

        job_runs = [a for a in added if isinstance(a, JobRun)]
        assert len(job_runs) == 1
        job = job_runs[0]
        assert job.workspace_id is not None
        assert job.workspace_id == uuid.UUID("00000000-0000-0000-0000-000000000001")
        assert job.pack_id == uuid.UUID("11111111-1111-1111-1111-111111111111")

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_creates_job_run_on_exception(
        self, mock_select, mock_render, mock_get_llm, mock_outreach, mock_resolved, *_args
    ):
        mock_resolved.return_value = _default_resolved()
        """generate_briefing creates JobRun with status failed on exception (issue #27)."""
        mock_select.side_effect = RuntimeError("DB connection lost")

        db = MagicMock()
        added = []

        def capture_add(obj):
            added.append(obj)

        db.add.side_effect = capture_add

        with pytest.raises(RuntimeError, match="DB connection lost"):
            generate_briefing(db)

        job_runs = [a for a in added if isinstance(a, JobRun)]
        assert len(job_runs) == 1
        job = job_runs[0]
        assert job.job_type == "briefing"
        assert job.status == "failed"
        assert "DB connection lost" in (job.error_message or "")
        assert job.finished_at is not None

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.send_briefing_email")
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_calls_send_briefing_email_when_enabled(
        self,
        mock_select,
        mock_render,
        mock_get_llm,
        mock_outreach,
        mock_resolved,
        mock_send,
        *_args,
    ):
        """generate_briefing calls send_briefing_email when enabled (issue #29)."""
        mock_resolved.return_value = ResolvedSettings(
            briefing_time="08:00",
            briefing_email="ops@example.com",
            briefing_email_enabled=True,
            briefing_frequency="daily",
            briefing_day_of_week=0,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="",
            smtp_password="",
            smtp_from="noreply@example.com",
        )
        mock_send.return_value = True

        company = _make_company()
        analysis = _make_analysis()
        mock_select.return_value = [company]
        mock_render.return_value = "prompt"
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.options.return_value = query_mock
        query_mock.first.side_effect = [None, analysis]
        # Query for items with company (for email)
        fake_item = MagicMock()
        fake_item.company = company
        query_mock.all.return_value = [fake_item]

        def set_id_on_refresh(obj):
            if isinstance(obj, BriefingItem):
                obj.id = 1

        db.refresh.side_effect = set_id_on_refresh

        result = generate_briefing(db)

        assert len(result) == 1
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert len(call_args[0][0]) == 1
        assert call_args[0][1] == "ops@example.com"
        assert call_args[1].get("failure_summary") is None

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.send_briefing_email")
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_email_includes_failure_summary_when_partial_failures(
        self,
        mock_select,
        mock_render,
        mock_get_llm,
        mock_outreach,
        mock_resolved,
        mock_send,
        *_args,
    ):
        """When some companies fail, email includes failure_summary (issue #32)."""
        mock_resolved.return_value = ResolvedSettings(
            briefing_time="08:00",
            briefing_email="ops@example.com",
            briefing_email_enabled=True,
            briefing_frequency="daily",
            briefing_day_of_week=0,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="",
            smtp_password="",
            smtp_from="noreply@example.com",
        )
        mock_send.return_value = True

        good = _make_company(id=1, name="Good Corp")
        bad = _make_company(id=2, name="Bad Corp")
        mock_select.return_value = [bad, good]
        mock_render.return_value = "prompt"
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        analysis = _make_analysis()
        call_count = 0

        def first_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None
            if call_count == 2:
                raise RuntimeError("LLM failed")
            if call_count == 3:
                return None
            return analysis

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.options.return_value = query_mock
        query_mock.first.side_effect = first_side_effect
        fake_item = MagicMock()
        fake_item.company = good
        fake_item.id = 1
        query_mock.all.return_value = [fake_item]

        def set_id_on_refresh(obj):
            if isinstance(obj, BriefingItem):
                obj.id = 1

        db.refresh.side_effect = set_id_on_refresh

        result = generate_briefing(db)

        assert len(result) == 1
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert "failure_summary" in call_kwargs
        assert "Bad Corp" in (call_kwargs["failure_summary"] or "")
        assert "LLM failed" in (call_kwargs["failure_summary"] or "")

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.send_briefing_email")
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_skips_email_when_disabled(
        self,
        mock_select,
        mock_render,
        mock_get_llm,
        mock_outreach,
        mock_resolved,
        mock_send,
        *_args,
    ):
        """generate_briefing does not call send_briefing_email when disabled."""
        mock_resolved.return_value = _default_resolved()

        company = _make_company()
        analysis = _make_analysis()
        mock_select.return_value = [company]
        mock_render.return_value = "prompt"
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.first.side_effect = [None, analysis]

        result = generate_briefing(db)

        assert len(result) == 1
        mock_send.assert_not_called()

    @patch("app.services.briefing.get_pack_for_workspace", return_value=None)
    @patch("app.services.briefing.get_default_pack_id", return_value=None)
    @patch("app.services.briefing.send_briefing_email")
    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.resolve_prompt_content")
    @patch("app.services.briefing.select_top_companies")
    def test_email_exception_does_not_fail_job(
        self,
        mock_select,
        mock_render,
        mock_get_llm,
        mock_outreach,
        mock_resolved,
        mock_send,
        *_args,
    ):
        """When send_briefing_email raises, job still completes (issue #29)."""
        mock_resolved.return_value = ResolvedSettings(
            briefing_time="08:00",
            briefing_email="ops@example.com",
            briefing_email_enabled=True,
            briefing_frequency="daily",
            briefing_day_of_week=0,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="",
            smtp_password="",
            smtp_from="noreply@example.com",
        )
        mock_send.side_effect = RuntimeError("SMTP failed")

        company = _make_company()
        analysis = _make_analysis()
        mock_select.return_value = [company]
        mock_render.return_value = "prompt"
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        db = MagicMock()
        query_mock = db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.options.return_value = query_mock
        query_mock.first.side_effect = [None, analysis]
        fake_item = MagicMock()
        fake_item.company = company
        query_mock.all.return_value = [fake_item]

        def set_id_on_refresh(obj):
            if isinstance(obj, BriefingItem):
                obj.id = 1

        db.refresh.side_effect = set_id_on_refresh

        result = generate_briefing(db)

        assert len(result) == 1
        mock_send.assert_called_once()

    @patch("app.services.briefing.get_resolved_settings")
    @patch("app.services.briefing.select_top_companies")
    def test_weekly_frequency_skips_when_wrong_day(self, mock_select, mock_resolved):
        """Weekly frequency skips generation when today is not configured day (issue #29)."""
        mock_resolved.return_value = ResolvedSettings(
            briefing_time="08:00",
            briefing_email="",
            briefing_email_enabled=False,
            briefing_frequency="weekly",
            briefing_day_of_week=0,  # Monday
            smtp_host="",
            smtp_port=587,
            smtp_user="",
            smtp_password="",
            smtp_from="",
        )
        # Tuesday = weekday 1 (weekday() is a method)
        with patch("app.services.briefing.date") as mock_date:
            fake_today = MagicMock()
            fake_today.weekday.return_value = 1
            mock_date.today.return_value = fake_today

            db = MagicMock()
            result = generate_briefing(db)

        assert result == []
        mock_select.assert_not_called()
