"""Tests for hallucination guardrails in outreach generation."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from app.models.analysis_record import AnalysisRecord
from app.models.company import Company
from app.models.operator_profile import OperatorProfile
from app.services.outreach import _validate_claims, generate_outreach

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROFILE_CONTENT = "# Fractional CTO\n15 years experience in scaling engineering teams"


def _make_company(**overrides):
    defaults = dict(
        id=1, name="Acme Corp", website_url="https://acme.example.com",
        founder_name="Jane Doe", notes="Early stage startup",
    )
    defaults.update(overrides)
    c = MagicMock(spec=Company)
    for k, v in defaults.items():
        setattr(c, k, v)
    return c


def _make_analysis(**overrides):
    defaults = dict(
        id=10, company_id=1, stage="scaling_team", stage_confidence=80,
        pain_signals_json={"top_risks": ["hiring"], "most_likely_next_problem": "Scaling", "recommended_conversation_angle": "Hiring"},
        evidence_bullets=["Hiring engineers"], explanation="Needs help",
    )
    defaults.update(overrides)
    a = MagicMock(spec=AnalysisRecord)
    for k, v in defaults.items():
        setattr(a, k, v)
    return a


def _make_mock_db(profile_content=PROFILE_CONTENT):
    db = MagicMock()
    if profile_content is not None:
        p = MagicMock(spec=OperatorProfile)
        p.content = profile_content
        db.query.return_value.first.return_value = p
    else:
        db.query.return_value.first.return_value = None
    return db


# ---------------------------------------------------------------------------
# _validate_claims unit tests
# ---------------------------------------------------------------------------


class TestValidateClaims:
    def test_exact_match(self):
        valid, invalid = _validate_claims(["15 years experience"], PROFILE_CONTENT)
        assert valid == ["15 years experience"]
        assert invalid == []

    def test_case_insensitive_match(self):
        valid, invalid = _validate_claims(["15 Years Experience"], PROFILE_CONTENT)
        assert valid == ["15 Years Experience"]
        assert invalid == []

    def test_no_matches(self):
        valid, invalid = _validate_claims(["built 50 startups", "PhD in AI"], PROFILE_CONTENT)
        assert valid == []
        assert invalid == ["built 50 startups", "PhD in AI"]

    def test_mixed_valid_and_invalid(self):
        valid, invalid = _validate_claims(
            ["scaling engineering teams", "invented the internet"],
            PROFILE_CONTENT,
        )
        assert valid == ["scaling engineering teams"]
        assert invalid == ["invented the internet"]

    def test_empty_claims(self):
        valid, invalid = _validate_claims([], PROFILE_CONTENT)
        assert valid == []
        assert invalid == []

    def test_empty_profile(self):
        valid, invalid = _validate_claims(["15 years experience"], "")
        assert valid == []
        assert invalid == ["15 years experience"]


# ---------------------------------------------------------------------------
# generate_outreach hallucination guardrail integration tests
# ---------------------------------------------------------------------------


class TestOutreachHallucinationGuardrail:
    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_valid_claims_no_retry(self, mock_render, mock_get_llm):
        """When all claims are valid, no retry is triggered."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.return_value = json.dumps({
            "subject": "Hello",
            "message": "Hi Jane",
            "operator_claims_used": ["15 years experience"],
        })

        db = _make_mock_db()
        result = generate_outreach(db, _make_company(), _make_analysis())

        assert result["subject"] == "Hello"
        assert result["message"] == "Hi Jane"
        mock_llm.complete.assert_called_once()  # No retry

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_hallucinated_claims_triggers_retry(self, mock_render, mock_get_llm, caplog):
        """When claims are hallucinated, a retry is triggered."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"

        # First call returns hallucinated claim; retry returns valid claim
        first_response = json.dumps({
            "subject": "Hello", "message": "Hi Jane",
            "operator_claims_used": ["built 50 startups"],
        })
        retry_response = json.dumps({
            "subject": "Hello v2", "message": "Hi Jane v2",
            "operator_claims_used": ["15 years experience"],
        })
        mock_llm.complete.side_effect = [first_response, retry_response]

        db = _make_mock_db()
        with caplog.at_level(logging.WARNING):
            result = generate_outreach(db, _make_company(), _make_analysis())

        assert result["subject"] == "Hello v2"

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_retry_still_hallucinated_strips_claims(self, mock_render, mock_get_llm, caplog):
        """When retry also has hallucinated claims, invalid claims are stripped."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"

        # Both calls return hallucinated claims
        bad_response = json.dumps({
            "subject": "Hello", "message": "Hi Jane",
            "operator_claims_used": ["built 50 startups", "15 years experience"],
        })
        still_bad_response = json.dumps({
            "subject": "Hello v2", "message": "Hi Jane v2",
            "operator_claims_used": ["invented AI"],
        })
        mock_llm.complete.side_effect = [bad_response, still_bad_response]

        db = _make_mock_db()
        with caplog.at_level(logging.WARNING):
            result = generate_outreach(db, _make_company(), _make_analysis())

        # Original message kept, invalid claims stripped
        assert result["subject"] == "Hello"
        assert result["message"] == "Hi Jane"
        assert mock_llm.complete.call_count == 2
        assert any("Retry still has hallucinated" in r.message for r in caplog.records)

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_no_claims_skips_validation(self, mock_render, mock_get_llm):
        """When no operator_claims_used, no validation is done."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.return_value = json.dumps({
            "subject": "Hello", "message": "Hi Jane",
            "operator_claims_used": [],
        })

        db = _make_mock_db()
        result = generate_outreach(db, _make_company(), _make_analysis())

        assert result["subject"] == "Hello"
        mock_llm.complete.assert_called_once()

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_retry_prompt_contains_hallucinated_claims(self, mock_render, mock_get_llm):
        """The retry prompt appends the hallucinated claims warning."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"

        first_response = json.dumps({
            "subject": "Hello", "message": "Hi Jane",
            "operator_claims_used": ["fake claim"],
        })
        retry_response = json.dumps({
            "subject": "Hello v2", "message": "Hi Jane v2",
            "operator_claims_used": [],
        })
        mock_llm.complete.side_effect = [first_response, retry_response]

        db = _make_mock_db()
        generate_outreach(db, _make_company(), _make_analysis())

        # Check the retry call's prompt contains the warning
        retry_call_args = mock_llm.complete.call_args_list[1]
        retry_prompt = retry_call_args[0][0]
        assert "fake claim" in retry_prompt
        assert "IMPORTANT" in retry_prompt
        assert "must not be used" in retry_prompt

    @patch("app.services.outreach.get_llm_provider")
    @patch("app.services.outreach.render_prompt")
    def test_word_count_shorten_includes_actual_message_not_regenerate(self, mock_render, mock_get_llm):
        """Word-count shorten prompt includes the message so LLM shortens it, not regenerates.

        Regeneration could reintroduce hallucinated claims from the earlier retry.
        """
        # First: hallucinated claim, retry returns valid but long message (>140 words)
        corrected_long_message = (
            "Hi Jane, I noticed you are scaling. With 15 years experience "
            + " ".join(["in engineering leadership"] * 50)  # 150+ words total
        )
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_render.return_value = "prompt"
        mock_llm.complete.side_effect = [
            json.dumps({
                "subject": "Hello",
                "message": "Bad message with fake claim " + " ".join(["x"] * 150),
                "operator_claims_used": ["built 50 startups"],
            }),
            json.dumps({
                "subject": "Hello v2",
                "message": corrected_long_message,
                "operator_claims_used": ["15 years experience"],
            }),
            json.dumps({
                "subject": "Hello v2",
                "message": "Hi Jane, I noticed you are scaling. With 15 years experience.",
                "operator_claims_used": ["15 years experience"],
            }),
        ]

        db = _make_mock_db()
        result = generate_outreach(db, _make_company(), _make_analysis())

        # Third call is the shorten call — must include the corrected message
        assert mock_llm.complete.call_count == 3
        shorten_prompt = mock_llm.complete.call_args_list[2][0][0]
        assert corrected_long_message in shorten_prompt
        assert "Shorten" in shorten_prompt or "140 words" in shorten_prompt
        assert "15 years experience" in result["message"]

