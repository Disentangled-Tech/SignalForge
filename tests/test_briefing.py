"""Tests for the daily briefing pipeline."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.orm import Session

from app.models.analysis_record import AnalysisRecord
from app.models.briefing_item import BriefingItem
from app.models.company import Company
from app.models.signal_record import SignalRecord
from app.services.briefing import (
    _ACTIVITY_WINDOW_DAYS,
    _DEDUP_WINDOW_DAYS,
    generate_briefing,
    select_top_companies,
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
    now = datetime.now(timezone.utc)
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
        created_at=datetime.now(timezone.utc),
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
        chain = (
            db.query.return_value.filter.return_value.filter.return_value
        )
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            companies
        )

        result = select_top_companies(db, limit=5)
        assert len(result) == 2
        # db.query is called multiple times (subqueries + main query).
        # Verify Company was queried by checking any call used Company.
        assert any(
            c.args[0] is Company
            for c in db.query.call_args_list
            if c.args
        )

    def test_respects_limit(self):
        db = MagicMock()
        chain = (
            db.query.return_value.filter.return_value.filter.return_value
        )
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )

        select_top_companies(db, limit=3)
        # Verify .limit(3) was called
        chain.filter.return_value.order_by.return_value.limit.assert_called_once_with(
            3
        )

    def test_returns_empty_when_no_companies(self):
        db = MagicMock()
        chain = (
            db.query.return_value.filter.return_value.filter.return_value
        )
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )

        result = select_top_companies(db)
        assert result == []

    def test_excludes_companies_without_analysis(self, db: Session):
        """Companies without AnalysisRecord are excluded (issue #22)."""
        now = datetime.now(timezone.utc)
        # Company with analysis
        c_with = Company(
            name="With Analysis",
            website_url="https://with.example.com",
            cto_need_score=80,
            last_scan_at=now - timedelta(days=2),
        )
        db.add(c_with)
        db.flush()
        db.add(
            AnalysisRecord(
                company_id=c_with.id,
                stage="scaling_team",
                pain_signals_json={},
                evidence_bullets=[],
                explanation="",
            )
        )
        # Company without analysis (has activity)
        c_without = Company(
            name="Without Analysis",
            website_url="https://without.example.com",
            cto_need_score=90,  # Higher score but no analysis
            last_scan_at=now - timedelta(days=2),
        )
        db.add(c_without)
        db.commit()

        result = select_top_companies(db, limit=5)
        ids = [c.id for c in result]
        assert c_with.id in ids
        assert c_without.id not in ids

    def test_exactly_up_to_limit(self, db: Session):
        """Returns up to limit; fewer when fewer qualify."""
        now = datetime.now(timezone.utc)
        for i in range(3):
            c = Company(
                name=f"Company {i}",
                website_url=f"https://c{i}.example.com",
                cto_need_score=70 - i,
                last_scan_at=now - timedelta(days=2),
            )
            db.add(c)
            db.flush()
            db.add(
                AnalysisRecord(
                    company_id=c.id,
                    stage="scaling_team",
                    pain_signals_json={},
                    evidence_bullets=[],
                    explanation="",
                )
            )
        db.commit()

        result = select_top_companies(db, limit=5)
        assert len(result) == 3  # Only 3 qualify
        result_2 = select_top_companies(db, limit=2)
        assert len(result_2) == 2

    def test_no_duplicates_in_7_days(self, db: Session):
        """Companies briefed in last 7 days are excluded."""
        now = datetime.now(timezone.utc)
        c = Company(
            name="Recently Briefed",
            website_url="https://recent.example.com",
            cto_need_score=95,
            last_scan_at=now - timedelta(days=2),
        )
        db.add(c)
        db.flush()
        analysis = AnalysisRecord(
            company_id=c.id,
            stage="scaling_team",
            pain_signals_json={},
            evidence_bullets=[],
            explanation="",
        )
        db.add(analysis)
        db.flush()
        db.add(
            BriefingItem(
                company_id=c.id,
                analysis_id=analysis.id,
                briefing_date=now.date(),
                created_at=now - timedelta(days=3),
            )
        )
        db.commit()

        result = select_top_companies(db, limit=5)
        assert c.id not in [x.id for x in result]

    def test_activity_within_14_days(self, db: Session):
        """Companies without recent activity are excluded."""
        now = datetime.now(timezone.utc)
        # Company with old last_scan_at and no recent signals
        c_old = Company(
            name="Old Activity",
            website_url="https://old.example.com",
            cto_need_score=90,
            last_scan_at=now - timedelta(days=20),  # Outside 14-day window
        )
        db.add(c_old)
        db.flush()
        db.add(
            AnalysisRecord(
                company_id=c_old.id,
                stage="scaling_team",
                pain_signals_json={},
                evidence_bullets=[],
                explanation="",
            )
        )
        # Company with recent activity
        c_recent = Company(
            name="Recent Activity",
            website_url="https://recent.example.com",
            cto_need_score=50,
            last_scan_at=now - timedelta(days=5),
        )
        db.add(c_recent)
        db.flush()
        db.add(
            AnalysisRecord(
                company_id=c_recent.id,
                stage="scaling_team",
                pain_signals_json={},
                evidence_bullets=[],
                explanation="",
            )
        )
        db.commit()

        result = select_top_companies(db, limit=5)
        ids = [x.id for x in result]
        assert c_recent.id in ids
        assert c_old.id not in ids

    def test_ordered_by_score_desc(self, db: Session):
        """Companies are ordered by cto_need_score descending."""
        now = datetime.now(timezone.utc)
        for score in [50, 90, 70]:
            c = Company(
                name=f"Score {score}",
                website_url=f"https://s{score}.example.com",
                cto_need_score=score,
                last_scan_at=now - timedelta(days=2),
            )
            db.add(c)
            db.flush()
            db.add(
                AnalysisRecord(
                    company_id=c.id,
                    stage="scaling_team",
                    pain_signals_json={},
                    evidence_bullets=[],
                    explanation="",
                )
            )
        db.commit()

        result = select_top_companies(db, limit=5)
        scores = [c.cto_need_score for c in result]
        assert scores == [90, 70, 50]


# ---------------------------------------------------------------------------
# generate_briefing
# ---------------------------------------------------------------------------


class TestGenerateBriefing:
    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.render_prompt")
    @patch("app.services.briefing.select_top_companies")
    def test_creates_briefing_items(
        self, mock_select, mock_render, mock_get_llm, mock_outreach
    ):
        company = _make_company()
        analysis = _make_analysis()
        mock_select.return_value = [company]
        mock_render.return_value = "prompt"

        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = analysis

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

    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.render_prompt")
    @patch("app.services.briefing.select_top_companies")
    def test_skips_company_without_analysis(
        self, mock_select, mock_render, mock_get_llm, mock_outreach
    ):
        company = _make_company()
        mock_select.return_value = [company]

        db = MagicMock()
        # No analysis record found.
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        result = generate_briefing(db)

        assert result == []
        mock_outreach.assert_not_called()

    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.render_prompt")
    @patch("app.services.briefing.select_top_companies")
    def test_one_failure_does_not_stop_others(
        self, mock_select, mock_render, mock_get_llm, mock_outreach
    ):
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

        def analysis_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("LLM exploded")
            return analysis

        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = analysis_side_effect

        result = generate_briefing(db)

        # Only the good company should have produced a briefing item.
        assert len(result) == 1

    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.render_prompt")
    @patch("app.services.briefing.select_top_companies")
    def test_llm_called_with_correct_temperature(
        self, mock_select, mock_render, mock_get_llm, mock_outreach
    ):
        company = _make_company()
        analysis = _make_analysis()
        mock_select.return_value = [company]
        mock_render.return_value = "prompt"

        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.complete.return_value = _VALID_BRIEFING_RESPONSE
        mock_outreach.return_value = _VALID_OUTREACH_RESULT

        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = analysis

        generate_briefing(db)

        mock_llm.complete.assert_called_once_with(
            "prompt",
            response_format={"type": "json_object"},
            temperature=0.5,
        )

    @patch("app.services.briefing.generate_outreach")
    @patch("app.services.briefing.get_llm_provider")
    @patch("app.services.briefing.render_prompt")
    @patch("app.services.briefing.select_top_companies")
    def test_empty_companies_returns_empty_list(
        self, mock_select, mock_render, mock_get_llm, mock_outreach
    ):
        mock_select.return_value = []

        db = MagicMock()
        result = generate_briefing(db)

        assert result == []
        mock_get_llm.assert_not_called()

