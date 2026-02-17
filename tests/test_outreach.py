"""Tests for the outreach message generator."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.analysis_record import AnalysisRecord
from app.models.company import Company
from app.models.operator_profile import OperatorProfile
from app.services.outreach import (
    _MAX_MESSAGE_WORDS,
    _truncate_to_word_limit,
    generate_outreach,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_OUTREACH_RESPONSE = json.dumps(
    {
        "subject": "Quick question about your scaling plans",
        "message": "Hi Jane, I noticed you are hiring engineers.",
        "operator_claims_used": ["15 years experience"],
        "company_specific_hooks": ["hiring engineers", "Series A"],
    }
)

_LONG_MESSAGE_RESPONSE = json.dumps(
    {
        "subject": "Subject",
        "message": " ".join(["word"] * 200),  # 200 words
        "operator_claims_used": [],
        "company_specific_hooks": [],
    }
)


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


def _make_analysis(**overrides):
    defaults = dict(
        id=10,
        company_id=1,
        stage="scaling_team",
        stage_confidence=80,
        pain_signals_json={
            "top_risks": ["hiring", "founder burnout"],
            "most_likely_next_problem": "Scaling the engineering team",
            "recommended_conversation_angle": "Engineering hiring strategy",
        },
        evidence_bullets=["Hiring 3 engineers", "Series A raised"],
        explanation="Needs help",
    )
    defaults.update(overrides)
    a = MagicMock(spec=AnalysisRecord)
    for k, v in defaults.items():
        setattr(a, k, v)
    return a


def _make_mock_db(operator_profile=None):
    db = MagicMock()
    db.query.return_value.first.return_value = operator_profile
    return db


def _make_operator_profile(content="# CTO\n15 years experience"):
    p = MagicMock(spec=OperatorProfile)
    p.content = content
    return p


# ---------------------------------------------------------------------------
# _truncate_to_word_limit
# ---------------------------------------------------------------------------


class TestTruncateToWordLimit:
    def test_under_limit_unchanged(self):
        text = "Hello world. How are you?"
        assert _truncate_to_word_limit(text, 10) == text

    def test_over_limit_truncates(self):
        text = "One two three four five six seven eight nine ten."
        result = _truncate_to_word_limit(text, 5)
        assert len(result.split()) <= 5

    def test_prefers_sentence_boundary(self):
        text = "First sentence. Second sentence. Third sentence."
        result = _truncate_to_word_limit(text, 4)
        assert result.endswith(".")
        assert "First sentence." in result or result == "First sentence."


# ---------------------------------------------------------------------------
# generate_outreach — happy path
# ---------------------------------------------------------------------------


class TestGenerateOutreachHappyPath:
    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_returns_subject_and_message(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.return_value = _VALID_OUTREACH_RESPONSE

        db = _make_mock_db(operator_profile=_make_operator_profile())
        result = generate_outreach(db, _make_company(), _make_analysis())

        assert result["subject"] == "Quick question about your scaling plans"
        assert "Jane" in result["message"]

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_llm_called_with_correct_params(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.return_value = _VALID_OUTREACH_RESPONSE

        db = _make_mock_db(operator_profile=_make_operator_profile())
        generate_outreach(db, _make_company(), _make_analysis())

        mock_llm.complete.assert_called_once_with(
            "prompt",
            response_format={"type": "json_object"},
            temperature=0.7,
        )

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_render_prompt_receives_all_placeholders(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.return_value = _VALID_OUTREACH_RESPONSE

        profile = _make_operator_profile("My profile text")
        db = _make_mock_db(operator_profile=profile)
        generate_outreach(db, _make_company(), _make_analysis())

        call_kwargs = mock_render.call_args[1]
        assert call_kwargs["OPERATOR_PROFILE_MARKDOWN"] == "My profile text"
        assert call_kwargs["COMPANY_NAME"] == "Acme Corp"
        assert call_kwargs["FOUNDER_NAME"] == "Jane Doe"
        assert call_kwargs["STAGE"] == "scaling_team"
        assert "hiring" in call_kwargs["TOP_RISKS"]
        assert call_kwargs["MOST_LIKELY_NEXT_PROBLEM"] == "Scaling the engineering team"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestGenerateOutreachEdgeCases:
    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_no_operator_profile_uses_empty_string(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.return_value = _VALID_OUTREACH_RESPONSE

        db = _make_mock_db(operator_profile=None)
        result = generate_outreach(db, _make_company(), _make_analysis())

        assert result["subject"] != ""
        call_kwargs = mock_render.call_args[1]
        assert call_kwargs["OPERATOR_PROFILE_MARKDOWN"] == ""

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_word_count_over_140_triggers_retry(self, mock_render, mock_get_llm, caplog):
        """When message > 140 words, shorten retry includes the actual message."""
        long_message = " ".join(["word"] * 200)
        short_response = json.dumps({
            "subject": "Short",
            "message": "Hi Jane. " + " ".join(["word"] * 70),
            "operator_claims_used": [],
            "company_specific_hooks": [],
        })
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.side_effect = [
            json.dumps({
                "subject": "Subject",
                "message": long_message,
                "operator_claims_used": [],
                "company_specific_hooks": [],
            }),
            short_response,
        ]

        db = _make_mock_db(operator_profile=_make_operator_profile())
        import logging
        with caplog.at_level(logging.WARNING):
            result = generate_outreach(db, _make_company(), _make_analysis())

        assert result["subject"] == "Short"
        assert len(result["message"].split()) <= _MAX_MESSAGE_WORDS
        assert mock_llm.complete.call_count == 2
        shorten_prompt = mock_llm.complete.call_args_list[1][0][0]
        assert "140 words" in shorten_prompt or "Shorten" in shorten_prompt
        # Bug fix: shorten prompt must include the actual message so LLM shortens it,
        # not regenerate (which could reintroduce hallucinated claims)
        assert long_message in shorten_prompt
        assert "---BEGIN MESSAGE---" in shorten_prompt

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_word_count_retry_still_over_truncates(self, mock_render, mock_get_llm):
        """When retry also exceeds 140 words, message is truncated."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.return_value = _LONG_MESSAGE_RESPONSE

        db = _make_mock_db(operator_profile=_make_operator_profile())
        result = generate_outreach(db, _make_company(), _make_analysis())

        assert len(result["message"].split()) <= _MAX_MESSAGE_WORDS
        assert mock_llm.complete.call_count == 2

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_word_count_under_140_no_retry(self, mock_render, mock_get_llm):
        """When message is under 140 words, no retry."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.return_value = _VALID_OUTREACH_RESPONSE

        db = _make_mock_db(operator_profile=_make_operator_profile())
        generate_outreach(db, _make_company(), _make_analysis())

        mock_llm.complete.assert_called_once()

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_llm_failure_returns_empty(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.side_effect = RuntimeError("LLM down")

        db = _make_mock_db(operator_profile=_make_operator_profile())
        result = generate_outreach(db, _make_company(), _make_analysis())

        assert result == {"subject": "", "message": ""}

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_invalid_json_returns_empty(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.return_value = "not valid json"

        db = _make_mock_db(operator_profile=_make_operator_profile())
        result = generate_outreach(db, _make_company(), _make_analysis())

        assert result == {"subject": "", "message": ""}

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_empty_pain_signals_still_works(self, mock_render, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.return_value = _VALID_OUTREACH_RESPONSE

        analysis = _make_analysis(pain_signals_json=None, evidence_bullets=None)
        db = _make_mock_db(operator_profile=_make_operator_profile())
        result = generate_outreach(db, _make_company(), analysis)

        assert result["subject"] != ""



