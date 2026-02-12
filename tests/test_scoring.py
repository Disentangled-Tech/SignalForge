"""Tests for the deterministic scoring engine."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.models.analysis_record import AnalysisRecord
from app.models.app_settings import AppSettings
from app.models.company import Company
from app.services.scoring import (
    DEFAULT_SIGNAL_WEIGHTS,
    STAGE_BONUSES,
    _is_signal_true,
    calculate_score,
    get_custom_weights,
    score_company,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _signals(true_keys: list[str] | None = None, nested: bool = True) -> dict:
    """Build a pain_signals dict with given keys set to true."""
    true_keys = true_keys or []
    sigs = {
        k: {"value": k in true_keys, "why": "test"}
        for k in DEFAULT_SIGNAL_WEIGHTS
    }
    if nested:
        return {"signals": sigs, "top_risks": [], "most_likely_next_problem": ""}
    return sigs


# ── calculate_score ──────────────────────────────────────────────────

class TestCalculateScore:
    """Tests for calculate_score()."""

    def test_all_false_no_stage_bonus(self) -> None:
        score = calculate_score(_signals([]), "mvp_building")
        assert score == 0

    def test_all_false_with_stage_bonus(self) -> None:
        score = calculate_score(_signals([]), "scaling_team")
        assert score == STAGE_BONUSES["scaling_team"]  # 20

    def test_all_true_capped_at_100(self) -> None:
        all_keys = list(DEFAULT_SIGNAL_WEIGHTS.keys())
        # Sum of all weights = 15+10+15+25+20+15+10 = 110
        # Plus enterprise_transition bonus = 30 → 140, capped at 100
        score = calculate_score(_signals(all_keys), "enterprise_transition")
        assert score == 100

    def test_specific_combination(self) -> None:
        # compliance_security_pressure(25) + product_delivery_issues(20) = 45
        # stage bonus for struggling_execution = 30 → total 75
        score = calculate_score(
            _signals(["compliance_security_pressure", "product_delivery_issues"]),
            "struggling_execution",
        )
        assert score == 75

    def test_single_signal(self) -> None:
        score = calculate_score(_signals(["hiring_engineers"]), "")
        assert score == 15

    def test_flat_signals_dict(self) -> None:
        """Flat dict (no 'signals' wrapper) should also work."""
        score = calculate_score(_signals(["founder_overload"], nested=False), "")
        assert score == 10

    def test_custom_weights_override(self) -> None:
        custom = {"hiring_engineers": 50, "founder_overload": 50}
        score = calculate_score(
            _signals(["hiring_engineers", "founder_overload"]),
            "",
            custom_weights=custom,
        )
        assert score == 100

    def test_custom_weights_ignore_defaults(self) -> None:
        """Custom weights replace defaults entirely — unknown default keys ignored."""
        custom = {"hiring_engineers": 10}
        # Even though compliance_security_pressure is true, custom doesn't have it
        score = calculate_score(
            _signals(["hiring_engineers", "compliance_security_pressure"]),
            "",
            custom_weights=custom,
        )
        assert score == 10

    def test_empty_pain_signals(self) -> None:
        assert calculate_score({}, "") == 0

    def test_non_dict_pain_signals(self) -> None:
        assert calculate_score("bad", "") == 0  # type: ignore[arg-type]
        assert calculate_score(None, "") == 0  # type: ignore[arg-type]
        assert calculate_score(42, "") == 0  # type: ignore[arg-type]

    def test_unknown_signal_keys_ignored(self) -> None:
        signals = {"signals": {"unknown_key": {"value": True, "why": "x"}}}
        score = calculate_score(signals, "")
        assert score == 0

    def test_negative_custom_weights(self) -> None:
        custom = {"hiring_engineers": -10}
        score = calculate_score(_signals(["hiring_engineers"]), "", custom_weights=custom)
        assert score == 0  # clamped to 0

    def test_flat_bool_values(self) -> None:
        """Accept flat bool values (not wrapped in dict)."""
        signals = {"hiring_engineers": True, "founder_overload": False}
        score = calculate_score(signals, "")
        assert score == 15

    def test_string_true_is_counted(self) -> None:
        """Regression: LLMs sometimes return string 'true' instead of boolean true.

        Previously entry.get('value') is True failed for string 'true', causing score 0.
        """
        signals = {
            "signals": {
                k: {"value": "true" if k in ("hiring_engineers", "founder_overload") else "false", "why": "test"}
                for k in DEFAULT_SIGNAL_WEIGHTS
            }
        }
        score = calculate_score(signals, "")
        assert score == 25  # hiring_engineers(15) + founder_overload(10)

    def test_is_signal_true_accepts_various_formats(self) -> None:
        """_is_signal_true accepts boolean, string, and int representations."""
        assert _is_signal_true(True) is True
        assert _is_signal_true("true") is True
        assert _is_signal_true("True") is True
        assert _is_signal_true("yes") is True
        assert _is_signal_true("1") is True
        assert _is_signal_true(1) is True
        assert _is_signal_true(1.0) is True
        assert _is_signal_true(False) is False
        assert _is_signal_true("false") is False
        assert _is_signal_true("no") is False
        assert _is_signal_true(0) is False
        assert _is_signal_true(None) is False

    def test_value_yes_is_counted(self) -> None:
        """String 'yes' is treated as truthy."""
        signals = {"signals": {"hiring_engineers": {"value": "yes", "why": "test"}}}
        assert calculate_score(signals, "") == 15

    def test_stage_case_insensitive(self) -> None:
        score = calculate_score(_signals([]), "Scaling_Team")
        assert score == 20

    def test_stage_whitespace_stripped(self) -> None:
        score = calculate_score(_signals([]), "  scaling_team  ")
        assert score == 20

    def test_minimum_zero(self) -> None:
        custom = {k: -100 for k in DEFAULT_SIGNAL_WEIGHTS}
        score = calculate_score(
            _signals(list(DEFAULT_SIGNAL_WEIGHTS.keys())), "", custom_weights=custom
        )
        assert score == 0


# ── get_custom_weights ───────────────────────────────────────────────

class TestGetCustomWeights:
    """Tests for get_custom_weights()."""

    def test_returns_dict_when_valid(self) -> None:
        row = MagicMock(spec=AppSettings)
        row.value = '{"hiring_engineers": 50}'
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        result = get_custom_weights(db)
        assert result == {"hiring_engineers": 50}

    def test_returns_none_when_missing(self) -> None:
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert get_custom_weights(db) is None

    def test_returns_none_when_value_is_none(self) -> None:
        row = MagicMock(spec=AppSettings)
        row.value = None
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        assert get_custom_weights(db) is None

    def test_returns_none_on_invalid_json(self) -> None:
        row = MagicMock(spec=AppSettings)
        row.value = "not-json{{"
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        assert get_custom_weights(db) is None

    def test_returns_none_when_json_is_not_dict(self) -> None:
        row = MagicMock(spec=AppSettings)
        row.value = "[1, 2, 3]"
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        assert get_custom_weights(db) is None


# ── score_company ────────────────────────────────────────────────────

class TestScoreCompany:
    """Tests for score_company()."""

    def test_updates_company_record(self) -> None:
        db = MagicMock()
        company = MagicMock(spec=Company)
        company.id = 1
        db.query.return_value.filter.return_value.first.side_effect = [
            None,   # get_custom_weights → no AppSettings row
            company,  # score_company → Company lookup
        ]

        analysis = MagicMock(spec=AnalysisRecord)
        analysis.pain_signals_json = _signals(["compliance_security_pressure"])
        analysis.stage = "scaling_team"

        score = score_company(db, 1, analysis)

        assert score == 45  # 25 (signal) + 20 (stage bonus)
        assert company.cto_need_score == 45
        assert company.current_stage == "scaling_team"
        db.commit.assert_called_once()

    def test_handles_missing_company(self) -> None:
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        analysis = MagicMock(spec=AnalysisRecord)
        analysis.pain_signals_json = _signals(["hiring_engineers"])
        analysis.stage = ""

        score = score_company(db, 999, analysis)
        assert score == 15  # still computes score
        db.commit.assert_not_called()

    def test_handles_none_pain_signals(self) -> None:
        db = MagicMock()
        company = MagicMock(spec=Company)
        company.id = 1
        db.query.return_value.filter.return_value.first.side_effect = [
            None,    # no custom weights
            company,
        ]

        analysis = MagicMock(spec=AnalysisRecord)
        analysis.pain_signals_json = None
        analysis.stage = None

        score = score_company(db, 1, analysis)
        assert score == 0
        assert company.cto_need_score == 0
        db.commit.assert_called_once()

    def test_uses_custom_weights_from_db(self) -> None:
        settings_row = MagicMock(spec=AppSettings)
        settings_row.value = '{"hiring_engineers": 99}'

        company = MagicMock(spec=Company)
        company.id = 1

        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [
            settings_row,  # get_custom_weights
            company,       # Company lookup
        ]

        analysis = MagicMock(spec=AnalysisRecord)
        analysis.pain_signals_json = _signals(["hiring_engineers"])
        analysis.stage = ""

        score = score_company(db, 1, analysis)
        assert score == 99
        assert company.cto_need_score == 99

