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
    @patch("app.services.analysis.resolve_prompt_content")
    def test_returns_analysis_record(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

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
    @patch("app.services.analysis.resolve_prompt_content")
    def test_render_prompt_called_with_correct_args(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"
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
        # resolve_prompt_content(template_name, pack, **kwargs)
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
    @patch("app.services.analysis.resolve_prompt_content")
    def test_raw_llm_response_stored(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"
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
    @patch("app.services.analysis.resolve_prompt_content")
    def test_no_operator_profile_uses_empty_string(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"
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


class TestAnalyzeCompanyPackParameter:
    """Phase 1: analyze_company accepts pack parameter; no behavior change yet."""

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.resolve_prompt_content")
    def test_accepts_pack_parameter_unchanged_behavior(self, mock_render, mock_get_llm) -> None:
        """Passing pack parameter does not change behavior; same prompts used."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"
        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        company = _make_company()
        signals = [_make_signal("Signal A")]
        db = _make_mock_db(company=company, signals=signals)

        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        result = analyze_company(db, company_id=1, pack=pack)

        assert result is not None
        assert result.stage == "scaling_team"
        # Phase 1: Same prompts used (stage_classification_v1, pain_signals_v1)
        assert mock_render.call_args_list[0][0][0] == "stage_classification_v1"
        assert mock_render.call_args_list[1][0][0] == "pain_signals_v1"


class TestAnalyzeCompanyEdgeCases:
    def test_company_not_found_returns_none(self):
        db = _make_mock_db(company=None)
        assert analyze_company(db, company_id=999) is None

    def test_no_signals_returns_none(self):
        db = _make_mock_db(company=_make_company(), signals=[])
        assert analyze_company(db, company_id=1) is None

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.resolve_prompt_content")
    def test_invalid_stage_defaults_to_early_customers(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

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
    @patch("app.services.analysis.resolve_prompt_content")
    def test_invalid_json_retries_and_succeeds(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

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
    @patch("app.services.analysis.resolve_prompt_content")
    def test_invalid_json_retry_also_fails_uses_defaults(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

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
    @patch("app.services.analysis.resolve_prompt_content")
    def test_pain_json_failure_uses_empty_dict(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

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
    @patch("app.services.analysis.resolve_prompt_content")
    def test_explanation_uses_temperature_07(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"
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
    @patch("app.services.analysis.resolve_prompt_content")
    def test_multiple_signals_concatenated(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"
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
# Explanation generator — Issue #18 acceptance criteria
# ---------------------------------------------------------------------------


class TestExplanationGeneratorIssue18:
    """Tests for Issue #18: explanation uses prompt template, anti-generic, 2-6 sentences."""

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.resolve_prompt_content")
    def test_explanation_uses_prompt_template(self, mock_render, mock_get_llm):
        """render_prompt is called with explanation_v1 and correct placeholders."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"
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

        # Third render_prompt call is explanation (after stage, pain)
        explanation_call = mock_render.call_args_list[2]
        assert explanation_call[0][0] == "explanation_v1"
        kwargs = explanation_call[1]
        assert kwargs["COMPANY_NAME"] == "Acme Corp"
        assert kwargs["STAGE"] == "scaling_team"
        assert "EVIDENCE_BULLETS" in kwargs
        assert "PAIN_SIGNALS_SUMMARY" in kwargs
        assert "TOP_RISKS" in kwargs
        assert "MOST_LIKELY_NEXT_PROBLEM" in kwargs

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.resolve_prompt_content")
    def test_explanation_includes_pain_data_context(self, mock_render, mock_get_llm):
        """Explanation prompt receives top_risks and most_likely_next_problem from pain_data."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"
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

        explanation_call = mock_render.call_args_list[2]
        kwargs = explanation_call[1]
        assert "hiring" in kwargs["TOP_RISKS"] or "founder burnout" in kwargs["TOP_RISKS"]
        assert "Scaling the engineering team" in kwargs["MOST_LIKELY_NEXT_PROBLEM"]

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.resolve_prompt_content")
    def test_explanation_handles_empty_pain_data(self, mock_render, mock_get_llm):
        """When pain_data has empty top_risks/most_likely_next_problem, placeholders get empty."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

        pain_no_risks = json.dumps({
            "signals": {"hiring_engineers": {"value": True, "why": "3 roles"}},
            "top_risks": [],
            "most_likely_next_problem": "",
            "uncertainties": [],
            "recommended_conversation_angle": "",
        })
        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,
            pain_no_risks,
            _EXPLANATION_TEXT,
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        analyze_company(db, company_id=1)

        explanation_call = mock_render.call_args_list[2]
        kwargs = explanation_call[1]
        assert kwargs["TOP_RISKS"] == ""
        assert kwargs["MOST_LIKELY_NEXT_PROBLEM"] == ""


def test_explanation_prompt_includes_anti_generic_guidance():
    """explanation_v1.md contains anti-generic wording per Issue #18 AC."""
    from app.prompts.loader import load_prompt

    content = load_prompt("explanation_v1")
    assert "generic" in content.lower()
    assert "specific" in content.lower()


def test_explanation_prompt_includes_2_6_sentences():
    """explanation_v1.md mentions 2-6 sentence requirement per Issue #18 AC."""
    from app.prompts.loader import load_prompt

    content = load_prompt("explanation_v1")
    assert "2" in content and "6" in content


# ---------------------------------------------------------------------------
# Stage classification — Issue #16 acceptance criteria
# ---------------------------------------------------------------------------


class TestStageClassificationIssue16:
    """Tests for Issue #16: returns one allowed stage, stored in AnalysisRecord."""

    @pytest.mark.parametrize("stage", sorted(ALLOWED_STAGES))
    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.resolve_prompt_content")
    def test_each_allowed_stage_stored_in_analysis_record(
        self, mock_render, mock_get_llm, stage
    ):
        """LLM returning each allowed stage results in correct stage in AnalysisRecord."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

        stage_response = json.dumps(
            {
                "stage": stage,
                "confidence": 75,
                "evidence_bullets": ["Evidence"],
                "assumptions": [],
            }
        )
        mock_llm.complete.side_effect = [
            stage_response,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        result = analyze_company(db, company_id=1)

        assert result is not None
        assert result.stage == stage
        add_call_args = db.add.call_args[0][0]
        assert isinstance(add_call_args, AnalysisRecord)
        assert add_call_args.stage == stage
        db.commit.assert_called_once()

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.resolve_prompt_content")
    def test_mixed_case_stage_normalized_to_lowercase(self, mock_render, mock_get_llm):
        """LLM returning 'Scaling_Team' (mixed case) results in stored 'scaling_team'."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

        mixed_case_response = json.dumps(
            {
                "stage": "Scaling_Team",
                "confidence": 80,
                "evidence_bullets": ["Hiring"],
                "assumptions": [],
            }
        )
        mock_llm.complete.side_effect = [
            mixed_case_response,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        result = analyze_company(db, company_id=1)

        assert result is not None
        assert result.stage == "scaling_team"
        add_call_args = db.add.call_args[0][0]
        assert add_call_args.stage == "scaling_team"

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.resolve_prompt_content")
    def test_non_string_stage_defaults_to_early_customers(self, mock_render, mock_get_llm):
        """LLM returning non-string stage (e.g. 123) defaults to early_customers."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

        non_string_response = json.dumps(
            {
                "stage": 123,
                "confidence": 50,
                "evidence_bullets": [],
                "assumptions": [],
            }
        )
        mock_llm.complete.side_effect = [
            non_string_response,
            _VALID_PAIN_RESPONSE,
            _EXPLANATION_TEXT,
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        result = analyze_company(db, company_id=1)

        assert result is not None
        assert result.stage == _DEFAULT_STAGE


# ---------------------------------------------------------------------------
# Pain signal detection — Issue #17 acceptance criteria
# ---------------------------------------------------------------------------


# Issue #17 canonical signals: hiring engineers, compliance, scaling issues, delivery problems
ISSUE_17_SIGNAL_KEYS = frozenset({
    "hiring_engineers",           # hiring engineers
    "compliance_security_pressure",  # compliance
    "architecture_scaling_risk",  # scaling issues
    "product_delivery_issues",     # delivery problems
})


class TestPainSignalDetectionIssue17:
    """Tests for Issue #17: four boolean signals detected and structured JSON stored."""

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.resolve_prompt_content")
    def test_four_issue_17_signals_stored_in_pain_signals_json(
        self, mock_render, mock_get_llm
    ):
        """LLM returning four Issue #17 signals results in structured JSON in pain_signals_json."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

        pain_response = json.dumps({
            "signals": {
                "hiring_engineers": {"value": True, "why": "3 open SWE roles"},
                "compliance_security_pressure": {"value": True, "why": "SOC2 mentioned"},
                "architecture_scaling_risk": {"value": True, "why": "Performance bottlenecks"},
                "product_delivery_issues": {"value": False, "why": "No evidence"},
            },
            "top_risks": ["hiring", "compliance"],
            "most_likely_next_problem": "Scaling the team",
            "uncertainties": [],
            "recommended_conversation_angle": "Compliance readiness",
        })
        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,
            pain_response,
            _EXPLANATION_TEXT,
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        result = analyze_company(db, company_id=1)

        assert result is not None
        pain = result.pain_signals_json
        assert pain is not None
        assert "signals" in pain

        signals = pain["signals"]
        for key in ISSUE_17_SIGNAL_KEYS:
            assert key in signals, f"Issue #17 signal '{key}' missing from stored JSON"
            entry = signals[key]
            assert isinstance(entry, dict), f"Signal '{key}' must be dict"
            assert "value" in entry, f"Signal '{key}' must have 'value'"
            assert isinstance(entry["value"], bool), f"Signal '{key}.value' must be bool"
            assert "why" in entry, f"Signal '{key}' must have 'why'"
            assert isinstance(entry["why"], str), f"Signal '{key}.why' must be str"

        assert "top_risks" in pain
        assert pain["top_risks"] == ["hiring", "compliance"]
        assert "most_likely_next_problem" in pain
        assert pain["most_likely_next_problem"] == "Scaling the team"

    @patch("app.services.analysis.get_llm_provider")
    @patch("app.services.analysis.resolve_prompt_content")
    def test_pain_signals_json_structure_persisted(self, mock_render, mock_get_llm):
        """Full pain signals JSON structure (signals, top_risks, etc.) is persisted."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.side_effect = lambda name, pack, **kw: f"prompt:{name}"

        pain_response = json.dumps({
            "signals": {
                "hiring_engineers": {"value": False, "why": ""},
                "compliance_security_pressure": {"value": False, "why": ""},
                "architecture_scaling_risk": {"value": True, "why": "Rewrites mentioned"},
                "product_delivery_issues": {"value": True, "why": "Missed timelines"},
            },
            "top_risks": ["delivery", "scaling"],
            "most_likely_next_problem": "Delivery problems",
            "uncertainties": ["Team size unknown"],
            "recommended_conversation_angle": "Delivery process",
        })
        mock_llm.complete.side_effect = [
            _VALID_STAGE_RESPONSE,
            pain_response,
            _EXPLANATION_TEXT,
        ]

        db = _make_mock_db(
            company=_make_company(),
            signals=[_make_signal()],
            operator_profile=_make_operator_profile(),
        )
        result = analyze_company(db, company_id=1)

        assert result is not None
        pain = result.pain_signals_json
        assert pain is not None
        assert pain["signals"]["architecture_scaling_risk"]["value"] is True
        assert pain["signals"]["product_delivery_issues"]["value"] is True
        assert pain["uncertainties"] == ["Team size unknown"]
        assert pain["recommended_conversation_angle"] == "Delivery process"


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

