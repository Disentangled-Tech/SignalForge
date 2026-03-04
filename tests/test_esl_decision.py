"""Unit tests for ESL decision module (Issue #175)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.esl.esl_decision import (
    CORE_BAN_SIGNAL_IDS,
    ESLDecisionResult,
    evaluate_esl_decision,
    get_effective_sensitivity_level,
)


def _pack(esl_policy: dict) -> SimpleNamespace:
    """Create minimal pack-like object with esl_policy."""
    return SimpleNamespace(esl_policy=esl_policy)


class TestEvaluateEslDecisionLegacy:
    """pack=None returns allow with reason legacy."""

    def test_pack_none_returns_allow(self) -> None:
        """Legacy path: pack=None → allow, reason_code=legacy."""
        result = evaluate_esl_decision(signal_ids={"funding_raised"}, pack=None)
        assert result.decision == "allow"
        assert result.reason_code == "legacy"
        assert result.sensitivity_level is None
        assert result.tone_constraint is None

    def test_pack_none_empty_signals(self) -> None:
        """Legacy path with empty signal_ids."""
        result = evaluate_esl_decision(signal_ids=set(), pack=None)
        assert result.decision == "allow"
        assert result.reason_code == "legacy"


class TestEvaluateEslDecisionBlockedSignals:
    """Pack blocked_signals → suppress."""

    def test_blocked_signal_suppresses(self) -> None:
        """Signal in blocked_signals → suppress, reason blocked_signal."""
        pack = _pack({"blocked_signals": ["distress_mentioned"]})
        result = evaluate_esl_decision(
            signal_ids={"funding_raised", "distress_mentioned"},
            pack=pack,
        )
        assert result.decision == "suppress"
        assert result.reason_code == "blocked_signal"

    def test_no_blocked_signal_allows(self) -> None:
        """No signal in blocked_signals → allow."""
        pack = _pack({"blocked_signals": ["distress_mentioned"]})
        result = evaluate_esl_decision(
            signal_ids={"funding_raised", "cto_role_posted"},
            pack=pack,
        )
        assert result.decision == "allow"
        assert result.reason_code == "none"

    def test_empty_blocked_signals_allows(self) -> None:
        """Empty blocked_signals → allow."""
        pack = _pack({"blocked_signals": []})
        result = evaluate_esl_decision(
            signal_ids={"funding_raised"},
            pack=pack,
        )
        assert result.decision == "allow"


class TestEvaluateEslDecisionProhibitedCombinations:
    """Pack prohibited_combinations → suppress."""

    def test_prohibited_pair_suppresses(self) -> None:
        """Both signals in prohibited pair present → suppress."""
        pack = _pack(
            {
                "prohibited_combinations": [["distress_mentioned", "bankruptcy_filed"]],
            }
        )
        result = evaluate_esl_decision(
            signal_ids={"distress_mentioned", "bankruptcy_filed"},
            pack=pack,
        )
        assert result.decision == "suppress"
        assert result.reason_code == "prohibited_combination"

    def test_prohibited_pair_order_agnostic(self) -> None:
        """Prohibited pair matches regardless of order in signal_ids."""
        pack = _pack(
            {
                "prohibited_combinations": [["a", "b"]],
            }
        )
        result = evaluate_esl_decision(signal_ids={"b", "a"}, pack=pack)
        assert result.decision == "suppress"

    def test_only_one_of_pair_allows(self) -> None:
        """Only one signal of prohibited pair → allow."""
        pack = _pack(
            {
                "prohibited_combinations": [["distress_mentioned", "bankruptcy_filed"]],
            }
        )
        result = evaluate_esl_decision(
            signal_ids={"distress_mentioned"},
            pack=pack,
        )
        assert result.decision == "allow"


class TestEvaluateEslDecisionDowngradeRules:
    """Pack downgrade_rules → allow_with_constraints."""

    def test_downgrade_rule_triggers_constraint(self) -> None:
        """Trigger signal present → allow_with_constraints, tone_constraint set."""
        pack = _pack(
            {
                "recommendation_boundaries": [
                    [0.0, "Observe Only"],
                    [0.7, "Standard Outreach"],
                    [0.9, "Direct Strategic Outreach"],
                ],
                "downgrade_rules": [
                    {
                        "trigger_signal": "high_sensitivity",
                        "max_recommendation": "Soft Value Share",
                    },
                ],
            }
        )
        result = evaluate_esl_decision(
            signal_ids={"funding_raised", "high_sensitivity"},
            pack=pack,
        )
        assert result.decision == "allow_with_constraints"
        assert result.reason_code == "downgrade_rule"
        assert result.tone_constraint == "Soft Value Share"

    def test_no_trigger_signal_allows(self) -> None:
        """Trigger signal not present → allow."""
        pack = _pack(
            {
                "downgrade_rules": [
                    {
                        "trigger_signal": "high_sensitivity",
                        "max_recommendation": "Soft Value Share",
                    },
                ],
            }
        )
        result = evaluate_esl_decision(
            signal_ids={"funding_raised"},
            pack=pack,
        )
        assert result.decision == "allow"


class TestEvaluateEslDecisionSensitivityMapping:
    """Pack sensitivity_mapping sets sensitivity_level."""

    def test_sensitivity_mapping_populated(self) -> None:
        """Signal in sensitivity_mapping → sensitivity_level set."""
        pack = _pack(
            {
                "sensitivity_mapping": {"distress_mentioned": "high"},
            }
        )
        result = evaluate_esl_decision(
            signal_ids={"funding_raised", "distress_mentioned"},
            pack=pack,
        )
        assert result.decision == "allow"
        assert result.sensitivity_level == "high"

    def test_no_sensitivity_mapping_returns_none(self) -> None:
        """No signals in mapping → sensitivity_level None."""
        pack = _pack({"sensitivity_mapping": {"other_signal": "high"}})
        result = evaluate_esl_decision(signal_ids={"funding_raised"}, pack=pack)
        assert result.sensitivity_level is None

    def test_core_taxonomy_sensitivity_when_pack_has_no_mapping(self) -> None:
        """When pack has no sensitivity_mapping, core taxonomy sensitivity is used (M2)."""
        pack = _pack({})
        result = evaluate_esl_decision(
            signal_ids={"founder_urgency_language"},
            pack=pack,
        )
        assert result.decision == "allow"
        # Core taxonomy has founder_urgency_language: medium
        assert result.sensitivity_level == "medium"


class TestEvaluateEslDecisionFractionalCto:
    """Fractional CTO pack (empty blocked/prohibited) → allow."""

    def test_fractional_cto_empty_policy_allows(self) -> None:
        """Empty blocked_signals and prohibited_combinations → allow."""
        pack = _pack(
            {
                "blocked_signals": [],
                "prohibited_combinations": [],
            }
        )
        result = evaluate_esl_decision(
            signal_ids={"funding_raised", "cto_role_posted", "job_posted_engineering"},
            pack=pack,
        )
        assert result.decision == "allow"
        assert result.reason_code == "none"

    def test_fractional_cto_omitted_keys_allows(self) -> None:
        """Omitted blocked/prohibited keys → allow."""
        pack = _pack({"recommendation_boundaries": [[0.0, "Observe Only"]]})
        result = evaluate_esl_decision(signal_ids={"funding_raised"}, pack=pack)
        assert result.decision == "allow"


class TestEvaluateEslDecisionOrder:
    """Logic order: core_ban > blocked > prohibited > downgrade > default."""

    def test_blocked_takes_precedence_over_downgrade(self) -> None:
        """Blocked signal suppresses even if downgrade would apply."""
        pack = _pack(
            {
                "blocked_signals": ["distress"],
                "downgrade_rules": [
                    {"trigger_signal": "distress", "max_recommendation": "Soft Value Share"},
                ],
            }
        )
        result = evaluate_esl_decision(signal_ids={"distress"}, pack=pack)
        assert result.decision == "suppress"
        assert result.reason_code == "blocked_signal"


class TestEslDecisionResult:
    """ESLDecisionResult dataclass."""

    def test_result_has_expected_fields(self) -> None:
        """ESLDecisionResult has decision, reason_code, sensitivity_level, tone_constraint."""
        r = ESLDecisionResult(
            decision="allow",
            reason_code="none",
            sensitivity_level=None,
            tone_constraint=None,
        )
        assert r.decision == "allow"
        assert r.reason_code == "none"
        assert r.sensitivity_level is None
        assert r.tone_constraint is None


class TestCoreBanSignalIds:
    """CORE_BAN_SIGNAL_IDS constant."""

    def test_core_ban_empty_phase1(self) -> None:
        """CORE_BAN_SIGNAL_IDS is empty for Phase 1."""
        assert CORE_BAN_SIGNAL_IDS == frozenset()


class TestGetEffectiveSensitivityLevel:
    """get_effective_sensitivity_level: core default + pack mapping merge (Issue #148 M2)."""

    def test_pack_only_returns_mapping_level(self) -> None:
        """Pack sensitivity_mapping only (core_taxonomy None) → same as legacy."""
        policy = {"sensitivity_mapping": {"distress_mentioned": "high"}}
        assert get_effective_sensitivity_level(
            signal_ids={"funding_raised", "distress_mentioned"},
            core_taxonomy=None,
            esl_policy=policy,
        ) == "high"

    def test_pack_only_no_overlap_returns_none(self) -> None:
        """Pack mapping with no overlapping signals → None."""
        policy = {"sensitivity_mapping": {"other_signal": "high"}}
        assert get_effective_sensitivity_level(
            signal_ids={"funding_raised"},
            core_taxonomy=None,
            esl_policy=policy,
        ) is None

    def test_core_only_returns_core_level(self) -> None:
        """Core taxonomy sensitivity only (no pack mapping) → core level."""
        core = {
            "signal_ids": ["founder_urgency_language", "funding_raised"],
            "signals": {"founder_urgency_language": {"sensitivity": "medium"}},
        }
        assert get_effective_sensitivity_level(
            signal_ids={"founder_urgency_language"},
            core_taxonomy=core,
            esl_policy={},
        ) == "medium"

    def test_core_only_no_sensitivity_in_core_returns_none(self) -> None:
        """Core has signals map but signal has no sensitivity → None."""
        core = {
            "signal_ids": ["funding_raised"],
            "signals": {"funding_raised": {}},
        }
        assert get_effective_sensitivity_level(
            signal_ids={"funding_raised"},
            core_taxonomy=core,
            esl_policy={},
        ) is None

    def test_pack_overrides_core_for_same_signal(self) -> None:
        """Pack sensitivity_mapping overrides core for same signal_id."""
        core = {
            "signal_ids": ["founder_urgency_language"],
            "signals": {"founder_urgency_language": {"sensitivity": "low"}},
        }
        policy = {"sensitivity_mapping": {"founder_urgency_language": "high"}}
        assert get_effective_sensitivity_level(
            signal_ids={"founder_urgency_language"},
            core_taxonomy=core,
            esl_policy=policy,
        ) == "high"

    def test_merge_highest_wins(self) -> None:
        """Multiple levels → highest wins (high > medium > low)."""
        core = {
            "signal_ids": ["a", "b", "c"],
            "signals": {"a": {"sensitivity": "low"}, "b": {"sensitivity": "medium"}},
        }
        policy = {"sensitivity_mapping": {"c": "high"}}
        assert get_effective_sensitivity_level(
            signal_ids={"a", "b", "c"},
            core_taxonomy=core,
            esl_policy=policy,
        ) == "high"

    def test_merge_core_only_highest_wins(self) -> None:
        """Core-only multiple levels → highest wins."""
        core = {
            "signal_ids": ["a", "b"],
            "signals": {"a": {"sensitivity": "medium"}, "b": {"sensitivity": "low"}},
        }
        assert get_effective_sensitivity_level(
            signal_ids={"a", "b"},
            core_taxonomy=core,
            esl_policy={},
        ) == "medium"

    def test_empty_signal_ids_returns_none(self) -> None:
        """Empty signal_ids → None."""
        policy = {"sensitivity_mapping": {"x": "high"}}
        assert get_effective_sensitivity_level(
            signal_ids=set(),
            core_taxonomy=None,
            esl_policy=policy,
        ) is None

    def test_invalid_pack_level_ignored(self) -> None:
        """Pack level not in low/medium/high is ignored (valid level still wins)."""
        core = {
            "signal_ids": ["a"],
            "signals": {"a": {"sensitivity": "medium"}},
        }
        policy = {"sensitivity_mapping": {"a": "invalid", "b": "high"}}
        assert get_effective_sensitivity_level(
            signal_ids={"a", "b"},
            core_taxonomy=core,
            esl_policy=policy,
        ) == "high"
