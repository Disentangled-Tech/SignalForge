"""Tests for the analysis pipeline (stage classification + pain signal detection)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest

from app.models.analysis_record import AnalysisRecord
from app.models.company import Company
from app.models.operator_profile import OperatorProfile
from app.models.signal_record import SignalRecord
from app.services.analysis import (
    ALLOWED_STAGES,
    _DEFAULT_STAGE,
    _parse_json_safe,
    analyze_company,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_VALID_STAGE_RESPONSE = json.dumps(
    {
        "stage": "scaling_team",
        "confidence": 82,
        "evidence_bullets": ["Hiring 3 engineers", "Series A raised"],
        "assumptions": ["Team size inferred from job posts"],
    }
)

_VALID_PAIN_RESPONSE = json.dumps(
    {
        "signals": {
            "hiring_engineers": {"value": True, "why": "3 open SWE roles"},
            "switching_from_agency": {"value": False, "why": "No evidence"},
            "adding_enterprise_features": {"value": True, "why": "SSO mentioned"},
            "compliance_security_pressure": {"value": False, "why": ""},
            "product_delivery_issues": {"value": False, "why": ""},
            "architecture_scaling_risk": {"value": False, "why": ""},
            "founder_overload": {"value": True, "why": "Wearing many hats"},
        },
        "top_risks": ["hiring", "founder burnout", "enterprise readiness"],
        "most_likely_next_problem": "Scaling the engineering team",
        "uncertainties": ["Actual team size unknown"],
        "recommended_conversation_angle": "Engineering hiring strategy",
    }
)

_EXPLANATION_TEXT = "This company is scaling and needs technical leadership."


def _make_mock_db(
    company: Company | None = None,
    signals: list[SignalRecord] | None = None,
    operator_profile: OperatorProfile | None = None,
):
    """Build a mock DB session that returns the given objects."""
    db = MagicMock()

    # query().filter().first() for Company
    # query().filter().all() for SignalRecord
    # query().first() for OperatorProfile
    def _query_side_effect(model):
        q = MagicMock()
        if model is Company:
            q.filter.return_value.first.return_value = company
        elif model is SignalRecord:
            q.filter.return_value.all.return_value = signals or []
        elif model is OperatorProfile:
            q.first.return_value = operator_profile
        return q

    db.query.side_effect = _query_side_effect
    return db


def _make_company(**overrides):
    defaults = dict(
        id=1,
        name="Acme Corp",
        website_url="https://acme.example.com",
        founder_name="Jane Doe",
        notes="Early stage startup",
    )
    defaults.update(overrides)
    c = MagicMock(spec=Company)
    for k, v in defaults.items():
        setattr(c, k, v)
    return c


def _make_signal(content_text: str = "We are hiring engineers"):
    s = MagicMock(spec=SignalRecord)
    s.content_text = content_text
    return s


def _make_operator_profile(content: str = "# Fractional CTO\n15 years experience"):
    p = MagicMock(spec=OperatorProfile)
    p.content = content
    return p


# ---------------------------------------------------------------------------
# _parse_json_safe
# ---------------------------------------------------------------------------


class TestParseJsonSafe:
    def test_valid_json(self):
        assert _parse_json_safe('{"a": 1}') == {"a": 1}

    def test_invalid_json(self):
        assert _parse_json_safe("not json") is None

    def test_empty_string(self):
        assert _parse_json_safe("") is None

    def test_none_input(self):
        assert _parse_json_safe(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# analyze_company — happy path
# ---------------------------------------------------------------------------


class TestAnalyzeCompanyHappyPath:
    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.render_prompt")
    def test_returns_analysis_record(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, **kw: f"prompt:{name}"

        # LLM calls: stage JSON, pain JSON, explanation text
        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        company = _make_company()
        signals = [_make_signal("Signal A"), _make_signal("Signal B")]
        profile = _make_operator_profile()
        db = _make_mock_db(company=company, signals=signals, operator_profile=profile)

        result = analyze_company(db, company_id=1)

        assert result is not None
        # Verify the AnalysisRecord was constructed correctly
        add_call_args = db.add.call_args[0][0]
        assert isinstance(add_call_args, AnalysisRecord)
        assert add_call_args.source_type == "full_analysis"
        assert add_call_args.stage == "scaling_team"
        assert add_call_args.stage_confidence == 82
        assert add_call_args.evidence_bullets == ["Hiring 3 engineers", "Series A raised"]
        assert add_call_args.explanation == _EXPLANATION_TEXT
        assert add_call_args.pain_signals_json is not None
        assert "signals" in add_call_args.pain_signals_json

        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.render_prompt")
    def test_render_prompt_called_with_correct_args(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, **kw: f"prompt:{name}"
        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        company = _make_company()
        signals = [_make_signal("Signal text")]
        profile = _make_operator_profile("My profile")
        db = _make_mock_db(company=company, signals=signals, operator_profile=profile)

        analyze_company(db, company_id=1)

        # Stage classification prompt
        stage_call = mock_render.call_args_list[0]
        assert stage_call[0][0] == "stage_classification_v1"
        assert stage_call[1]["COMPANY_NAME"] == "Acme Corp"
        assert stage_call[1]["WEBSITE_URL"] == "https://acme.example.com"
        assert stage_call[1]["FOUNDER_NAME"] == "Jane Doe"
        assert stage_call[1]["COMPANY_NOTES"] == "Early stage startup"
        assert stage_call[1]["SIGNALS_TEXT"] == "Signal text"
        assert stage_call[1]["OPERATOR_PROFILE_MARKDOWN"] == "My profile"

        # Pain signals prompt
        pain_call = mock_render.call_args_list[1]
        assert pain_call[0][0] == "pain_signals_v1"
        assert pain_call[1]["COMPANY_NAME"] == "Acme Corp"
        assert pain_call[1]["SIGNALS_TEXT"] == "Signal text"

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.render_prompt")
    def test_raw_llm_response_stored(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, **kw: f"prompt:{name}"
        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        analyze_company(db, company_id=1)

        record = db.add.call_args[0][0]
        assert _VALID_STAGE_RESPONSE in record.raw_llm_response
        assert _VALID_PAIN_RESPONSE in record.raw_llm_response

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.render_prompt")
    def test_no_operator_profile_uses_empty_string(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, **kw: f"prompt:{name}"
        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=None,
        )
        analyze_company(db, company_id=1)

        stage_call = mock_render.call_args_list[0]
        assert stage_call[1]["OPERATOR_PROFILE_MARKDOWN"] == ""


# ---------------------------------------------------------------------------
# analyze_company — edge cases
# ---------------------------------------------------------------------------


class TestAnalyzeCompanyEdgeCases:
    def test_company_not_found_returns_none(self):
        db = _make_mock_db(company=None)
        assert analyze_company(db, company_id=999) is None

    def test_no_signals_returns_none(self):
        db = _make_mock_db(company=_make_company(), signals=[])
        assert analyze_company(db, company_id=1) is None

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.render_prompt")
    def test_invalid_stage_defaults_to_early_customers(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, **kw: f"prompt:{name}"

        bad_stage_response = json.dumps(
            {
                "stage": "totally_invalid_stage",
                "confidence": 50,
                "evidence_bullets": ["Some evidence"],
                "assumptions": [],
            }
        )
        mock_llm.complete.side_effect = [
            bad_stage_response,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        analyze_company(db, company_id=1)

        record = db.add.call_args[0][0]
        assert record.stage == _DEFAULT_STAGE

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.render_prompt")
    def test_invalid_json_retries_and_succeeds(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, **kw: f"prompt:{name}"

        # First call returns invalid JSON, retry returns valid
        mock_llm.complete.side_effect = [
            "not valid json at all",  # stage first attempt
            _VALID_STAGE_RESPONSE,    # stage retry
            _VALID_PAIN_RESPONSE,     # pain first attempt (succeeds)
            _EXPLANATION_TEXT,         # explanation
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        analyze_company(db, company_id=1)

        record = db.add.call_args[0][0]
        assert record.stage == "scaling_team"
        # LLM was called 4 times: stage(fail) + stage(retry) + pain + explanation
        assert mock_llm.complete.call_count == 4

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.render_prompt")
    def test_invalid_json_retry_also_fails_uses_defaults(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, **kw: f"prompt:{name}"

        # Both stage attempts fail, pain succeeds
        mock_llm.complete.side_effect = [
            "bad json 1",             # stage first attempt
            "bad json 2",             # stage retry
            _VALID_PAIN_RESPONSE,     # pain
            _EXPLANATION_TEXT,         # explanation
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        analyze_company(db, company_id=1)

        record = db.add.call_args[0][0]
        assert record.stage == _DEFAULT_STAGE
        assert record.stage_confidence == 0
        assert record.evidence_bullets == []

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.render_prompt")
    def test_pain_json_failure_uses_empty_dict(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, **kw: f"prompt:{name}"

        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,    # stage succeeds
            "not json",               # pain first attempt
            "still not json",         # pain retry
            _EXPLANATION_TEXT,         # explanation
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        analyze_company(db, company_id=1)

        record = db.add.call_args[0][0]
        assert record.pain_signals_json == {}

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.render_prompt")
    def test_explanation_uses_temperature_07(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, **kw: f"prompt:{name}"
        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        analyze_company(db, company_id=1)

        # The third call is the explanation — should use temperature=0.7
        explanation_call = mock_llm.complete.call_args_list[2]
        assert explanation_call[1]["temperature"] == 0.7

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.render_prompt")
    def test_multiple_signals_concatenated(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, **kw: f"prompt:{name}"
        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        signals = [_make_signal("Signal A"), _make_signal("Signal B"), _make_signal("Signal C")]
        db = _make_mock_db(
            company=_make_company(),
            signals=signals,
            operator_profile=_make_operator_profile(),
        )
        analyze_company(db, company_id=1)

        stage_call = mock_render.call_args_list[0]
        expected_text = "Signal A\n\n---\n\nSignal B\n\n---\n\nSignal C"
        assert stage_call[1]["SIGNALS_TEXT"] == expected_text


# ---------------------------------------------------------------------------
# ALLOWED_STAGES constant
# ---------------------------------------------------------------------------


class TestAllowedStages:
    def test_contains_all_six_stages(self):
        expected = {
            "idea", "mvp_building", "early_customers",
            "scaling_team", "enterprise_transition", "struggling_execution",
        }
        assert ALLOWED_STAGES == expected

    def test_default_stage_is_in_allowed(self):
        assert _DEFAULT_STAGE in ALLOWED_STAGES

