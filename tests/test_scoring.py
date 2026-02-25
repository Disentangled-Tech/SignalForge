"""Tests for the deterministic scoring engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models.analysis_record import AnalysisRecord
from app.models.app_settings import AppSettings
from app.models.company import Company
from app.services.scoring import (
    _is_signal_true,
    calculate_score,
    get_custom_weights,
    get_display_scores_for_companies,
    score_company,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _get_cto_pack_keys() -> list[str]:
    """Return pain signal keys from fractional_cto_v1 pack (Phase 2)."""
    try:
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        return list((pack.scoring or {}).get("pain_signal_weights") or {})
    except (FileNotFoundError, ValueError, KeyError):
        return [
            "hiring_engineers",
            "switching_from_agency",
            "adding_enterprise_features",
            "compliance_security_pressure",
            "product_delivery_issues",
            "architecture_scaling_risk",
            "founder_overload",
        ]


def _get_cto_stage_bonuses() -> dict[str, int]:
    """Return stage bonuses from fractional_cto_v1 pack (Phase 2)."""
    try:
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        return dict((pack.scoring or {}).get("stage_bonuses") or {})
    except (FileNotFoundError, ValueError, KeyError):
        return {"scaling_team": 20, "enterprise_transition": 30, "struggling_execution": 30}


def _signals(true_keys: list[str] | None = None, nested: bool = True) -> dict:
    """Build a pain_signals dict with given keys set to true."""
    true_keys = true_keys or []
    keys = _get_cto_pack_keys()
    sigs = {k: {"value": k in true_keys, "why": "test"} for k in keys}
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
        assert score == _get_cto_stage_bonuses()["scaling_team"]  # 20

    def test_all_true_capped_at_100(self) -> None:
        all_keys = _get_cto_pack_keys()
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

    def test_custom_weights_merge_with_defaults(self) -> None:
        """Custom weights override specified keys; unspecified use defaults (Issue #64)."""
        custom = {"hiring_engineers": 10}
        score = calculate_score(
            _signals(["hiring_engineers", "compliance_security_pressure"]),
            "",
            custom_weights=custom,
        )
        # hiring_engineers: 10 (custom), compliance: 25 (default)
        assert score == 35

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

    def test_cto_score_non_zero_when_signals_present(self) -> None:
        """Regression: CTO score must be non-zero when pain signals are true.

        Fails if scoring ignores valid signals (e.g. string \"true\" vs boolean).
        """
        signals = _signals(["hiring_engineers", "founder_overload"])
        score = calculate_score(signals, "")
        assert score != 0, (
            "CTO score must be non-zero when pain signals are present. "
            'Check that value parsing accepts both boolean True and string "true".'
        )
        assert score == 25  # hiring_engineers(15) + founder_overload(10)

    def test_string_true_is_counted(self) -> None:
        """Regression: LLMs sometimes return string 'true' instead of boolean true.

        Previously entry.get('value') is True failed for string 'true', causing score 0.
        """
        signals = {
            "signals": {
                k: {
                    "value": "true" if k in ("hiring_engineers", "founder_overload") else "false",
                    "why": "test",
                }
                for k in _get_cto_pack_keys()
            }
        }
        score = calculate_score(signals, "")
        assert score != 0, (
            "String \"true\" must be counted. Scoring likely uses 'is True' instead of "
            "_is_signal_true()."
        )
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
        keys = _get_cto_pack_keys()
        custom = dict.fromkeys(keys, -100)
        score = calculate_score(_signals(keys), "", custom_weights=custom)
        assert score == 0

    def test_returns_int_with_float_weights(self) -> None:
        """Score is always int even when custom weights are floats (e.g. from JSON)."""
        custom = {"hiring_engineers": 15.5, "founder_overload": 10.3}
        score = calculate_score(
            _signals(["hiring_engineers", "founder_overload"]),
            "",
            custom_weights=custom,
        )
        assert isinstance(score, int)
        assert 0 <= score <= 100
        assert score == 26  # 15.5 + 10.3 = 25.8, rounded to 26


# ── get_custom_weights ───────────────────────────────────────────────


class TestGetCustomWeights:
    """Tests for get_custom_weights()."""

    def test_returns_dict_when_valid(self) -> None:
        row = MagicMock(spec=AppSettings)
        row.value = '{"hiring_engineers": 50}'
        db = MagicMock()
        # Phase 2: get_default_pack_id first (returns None), then AppSettings (returns row)
        db.query.return_value.filter.return_value.first.side_effect = [None, row]
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
        db.query.return_value.filter.return_value.first.side_effect = [None, row]
        assert get_custom_weights(db) is None

    def test_returns_none_on_invalid_json(self) -> None:
        row = MagicMock(spec=AppSettings)
        row.value = "not-json{{"
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [None, row]
        assert get_custom_weights(db) is None

    def test_returns_none_when_json_is_not_dict(self) -> None:
        row = MagicMock(spec=AppSettings)
        row.value = "[1, 2, 3]"
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [None, row]
        assert get_custom_weights(db) is None


# ── get_display_scores_for_companies ──────────────────────────────────


class TestGetDisplayScoresForCompanies:
    """Tests for get_display_scores_for_companies()."""

    def test_empty_company_ids_returns_empty_dict(self) -> None:
        db = MagicMock()
        result = get_display_scores_for_companies(db, [])
        assert result == {}

    @patch("app.services.score_resolver.get_company_scores_batch")
    def test_returns_scores_from_latest_analysis_per_company(self, mock_batch) -> None:
        """Phase 2: get_display_scores_for_companies uses batched get_company_scores_batch."""
        mock_batch.return_value = {1: 35, 2: 30}

        db = MagicMock()
        result = get_display_scores_for_companies(db, [1, 2])
        assert result == {1: 35, 2: 30}
        mock_batch.assert_called_once_with(db, [1, 2])

    @patch("app.services.score_resolver.get_company_scores_batch")
    def test_uses_latest_analysis_when_multiple_exist(self, mock_batch) -> None:
        """Phase 2: get_company_scores_batch returns cto_need_score when no ReadinessSnapshot."""
        mock_batch.return_value = {1: 35}

        db = MagicMock()
        result = get_display_scores_for_companies(db, [1])
        assert result == {1: 35}
        mock_batch.assert_called_once_with(db, [1])

    @patch("app.services.score_resolver.get_company_scores_batch")
    def test_uses_custom_weights_when_set(self, mock_batch) -> None:
        """Phase 2: get_company_scores_batch returns cto_need_score (which may reflect custom weights)."""
        mock_batch.return_value = {1: 99}

        db = MagicMock()
        result = get_display_scores_for_companies(db, [1])
        assert result == {1: 99}
        mock_batch.assert_called_once_with(db, [1])


# ── score_company ────────────────────────────────────────────────────


class TestScoreCompany:
    """Tests for score_company()."""

    def test_updates_company_record(self) -> None:
        db = MagicMock()
        company = MagicMock(spec=Company)
        company.id = 1
        # Phase 2: get_custom_weights (2); get_default_pack_id (1); calculate_score (1); Company lookup (1)
        db.query.return_value.filter.return_value.first.side_effect = [
            None,
            None,
            None,
            None,
            company,
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
            None,
            None,
            None,
            None,
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
            None,
            settings_row,
            None,
            None,
            company,
        ]

        analysis = MagicMock(spec=AnalysisRecord)
        analysis.pain_signals_json = _signals(["hiring_engineers"])
        analysis.stage = ""

        score = score_company(db, 1, analysis)
        assert score == 99
        assert company.cto_need_score == 99


# ── Issue #64: All company scores zero ─────────────────────────────────────


class TestIssue64ZeroScores:
    """Regression tests for Issue #64: custom weights/legacy keys causing score 0."""

    def test_detected_key_accepted_as_legacy(self) -> None:
        """Signals with 'detected' instead of 'value' produce non-zero score."""
        signals = {
            "signals": {
                "hiring_engineers": {"detected": True, "why": "legacy format"},
                "founder_overload": {"detected": False, "why": "no evidence"},
            }
        }
        score = calculate_score(signals, "")
        assert score != 0, "Legacy 'detected' key must be counted"
        assert score == 15  # hiring_engineers weight

    def test_legacy_signal_keys_mapped_to_canonical(self) -> None:
        """Analysis with hiring_technical_roles maps to hiring_engineers."""
        signals = {
            "signals": {
                "hiring_technical_roles": {"value": True, "why": "old key"},
                "compliance_needs": {"value": True, "why": "old key"},
            }
        }
        score = calculate_score(signals, "")
        assert score != 0
        assert score == 40  # hiring_engineers(15) + compliance_security_pressure(25)

    def test_legacy_recent_funding_maps_to_architecture_scaling_risk(self) -> None:
        """recent_funding (capital received, scaling needs) maps to architecture_scaling_risk.

        Not switching_from_agency (agency→in-house) — semantically different signals.
        """
        signals = {
            "signals": {
                "recent_funding": {"value": True, "why": "Series A announced"},
            }
        }
        score = calculate_score(signals, "")
        assert score == 15  # architecture_scaling_risk weight

    def test_custom_weights_with_legacy_keys_merge_with_defaults(self) -> None:
        """Custom weights with legacy keys still produce non-zero score (merge fix)."""
        db = MagicMock()
        settings_row = MagicMock(spec=AppSettings)
        settings_row.value = '{"hiring_technical_roles": 50, "compliance_needs": 30}'
        db.query.return_value.filter.return_value.first.side_effect = [None, settings_row]

        custom = get_custom_weights(db)
        assert custom is not None
        assert "hiring_engineers" in custom
        assert custom["hiring_engineers"] == 50
        assert custom["compliance_security_pressure"] == 30

        signals = {
            "signals": {
                "hiring_engineers": {"value": True, "why": "test"},
                "compliance_security_pressure": {"value": True, "why": "test"},
            }
        }
        score = calculate_score(signals, "", custom_weights=custom)
        assert score == 80  # 50 + 30

    def test_custom_weights_partial_override_uses_defaults_for_rest(self) -> None:
        """Custom weights override only specified keys; rest use defaults."""
        custom = {"hiring_engineers": 50}
        signals = _signals(["hiring_engineers", "founder_overload"])
        score = calculate_score(signals, "", custom_weights=custom)
        assert score == 60  # 50 (custom) + 10 (founder_overload from default)

    def test_all_zero_when_custom_weights_had_wrong_keys_now_fixed(self) -> None:
        """Before fix: custom weights with only wrong keys caused score 0.
        After fix: we merge with defaults, so canonical keys from analysis still score.
        """
        # Simulate old custom weights that had ONLY legacy keys (now normalized)
        custom = {"hiring_engineers": 20}  # User overrode one key
        signals = {
            "signals": {
                "hiring_engineers": {"value": True, "why": "test"},
                "compliance_security_pressure": {"value": True, "why": "test"},
            }
        }
        score = calculate_score(signals, "scaling_team", custom_weights=custom)
        assert score != 0
        # hiring_engineers: 20 (custom), compliance: 25 (default), stage: 20
        assert score == 65


# ── Integration: score_company updates company record in DB ─────────────


@pytest.mark.integration
class TestScoreCompanyIntegration:
    """Integration tests proving company.cto_need_score is updated correctly (Issue #21)."""

    def test_score_company_updates_company_record_in_db(self, db) -> None:
        """Latest analysis updates company.cto_need_score and current_stage in DB."""
        from app.models.analysis_record import AnalysisRecord
        from app.models.company import Company

        company = Company(
            name="Integration Test Co",
            website_url="https://example.com",
            source="manual",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        analysis = AnalysisRecord(
            company_id=company.id,
            source_type="full_analysis",
            stage="scaling_team",
            pain_signals_json=_signals(["hiring_engineers", "compliance_security_pressure"]),
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        # Before: company has no score
        assert company.cto_need_score is None
        assert company.current_stage is None

        score_company(db, company.id, analysis)

        # After: company record updated in DB
        db.refresh(company)
        assert company.cto_need_score == 60  # 15 + 25 (signals) + 20 (stage bonus)
        assert company.current_stage == "scaling_team"
