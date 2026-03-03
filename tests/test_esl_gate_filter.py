"""Tests for ESL gate filter (Issue #175, Phase 3/4)."""

from __future__ import annotations

from app.services.esl.esl_gate_filter import (
    apply_tone_constraint,
    get_effective_engagement_type,
    get_esl_decision_from_explain,
    is_suppressed,
    is_suppressed_from_engagement,
)


class TestGetEslDecisionFromExplain:
    """Tests for get_esl_decision_from_explain."""

    def test_returns_allow_when_present(self) -> None:
        assert get_esl_decision_from_explain({"esl_decision": "allow"}) == "allow"

    def test_returns_suppress_when_present(self) -> None:
        assert get_esl_decision_from_explain({"esl_decision": "suppress"}) == "suppress"

    def test_returns_allow_with_constraints_when_present(self) -> None:
        assert (
            get_esl_decision_from_explain({"esl_decision": "allow_with_constraints"})
            == "allow_with_constraints"
        )

    def test_returns_none_when_missing(self) -> None:
        assert get_esl_decision_from_explain({}) is None
        assert get_esl_decision_from_explain({"other": "x"}) is None

    def test_returns_none_when_explain_none(self) -> None:
        assert get_esl_decision_from_explain(None) is None


class TestIsSuppressed:
    """Tests for is_suppressed."""

    def test_true_when_suppress(self) -> None:
        assert is_suppressed({"esl_decision": "suppress"}) is True

    def test_false_when_allow(self) -> None:
        assert is_suppressed({"esl_decision": "allow"}) is False

    def test_false_when_allow_with_constraints(self) -> None:
        assert is_suppressed({"esl_decision": "allow_with_constraints"}) is False

    def test_false_when_missing(self) -> None:
        assert is_suppressed({}) is False
        assert is_suppressed(None) is False


class TestApplyToneConstraint:
    """Tests for apply_tone_constraint."""

    def test_returns_unchanged_when_no_constraint(self) -> None:
        assert apply_tone_constraint("Standard Outreach", None) == "Standard Outreach"

    def test_caps_higher_to_constraint(self) -> None:
        assert apply_tone_constraint("Standard Outreach", "Soft Value Share") == "Soft Value Share"
        assert (
            apply_tone_constraint("Direct Strategic Outreach", "Low-Pressure Intro")
            == "Low-Pressure Intro"
        )

    def test_unchanged_when_already_lower(self) -> None:
        assert apply_tone_constraint("Observe Only", "Soft Value Share") == "Observe Only"
        assert apply_tone_constraint("Soft Value Share", "Standard Outreach") == "Soft Value Share"

    def test_same_level_unchanged(self) -> None:
        assert apply_tone_constraint("Soft Value Share", "Soft Value Share") == "Soft Value Share"


class TestGetEffectiveEngagementType:
    """Tests for get_effective_engagement_type."""

    def test_unchanged_when_allow(self) -> None:
        assert (
            get_effective_engagement_type(
                "Standard Outreach",
                {"esl_decision": "allow"},
            )
            == "Standard Outreach"
        )

    def test_unchanged_when_missing_decision(self) -> None:
        assert get_effective_engagement_type("Standard Outreach", {}) == "Standard Outreach"

    def test_capped_when_allow_with_constraints(self) -> None:
        assert (
            get_effective_engagement_type(
                "Standard Outreach",
                {"esl_decision": "allow_with_constraints", "tone_constraint": "Soft Value Share"},
            )
            == "Soft Value Share"
        )


class TestIsSuppressedFromEngagement:
    """Phase 4: prefer column over explain."""

    def test_column_suppress_returns_true(self) -> None:
        """esl_decision='suppress' column → True regardless of explain."""
        assert is_suppressed_from_engagement("suppress", None) is True
        assert is_suppressed_from_engagement("suppress", {"esl_decision": "allow"}) is True

    def test_column_allow_falls_back_to_explain(self) -> None:
        """esl_decision='allow' or None → check explain."""
        assert is_suppressed_from_engagement("allow", {"esl_decision": "suppress"}) is True
        assert is_suppressed_from_engagement(None, {"esl_decision": "suppress"}) is True
        assert is_suppressed_from_engagement("allow", {"esl_decision": "allow"}) is False
        assert is_suppressed_from_engagement(None, None) is False

    def test_column_allow_with_constraints_not_suppressed(self) -> None:
        """allow_with_constraints is not suppress."""
        assert is_suppressed_from_engagement("allow_with_constraints", None) is False


class TestGetEffectiveEngagementTypeWithColumn:
    """Phase 4: esl_decision param prefers column."""

    def test_allow_with_constraints_caps_at_tone(self) -> None:
        """When esl_decision=allow_with_constraints, tone_constraint caps."""
        result = get_effective_engagement_type(
            "Standard Outreach",
            {"tone_constraint": "Soft Value Share"},
            esl_decision="allow_with_constraints",
        )
        assert result == "Soft Value Share"

    def test_allow_with_constraints_from_explain_when_column_none(self) -> None:
        """When column None, falls back to explain."""
        result = get_effective_engagement_type(
            "Standard Outreach",
            {"esl_decision": "allow_with_constraints", "tone_constraint": "Soft Value Share"},
            esl_decision=None,
        )
        assert result == "Soft Value Share"

    def test_allow_returns_unchanged(self) -> None:
        """allow → engagement_type unchanged."""
        result = get_effective_engagement_type(
            "Standard Outreach",
            {"tone_constraint": "Soft Value Share"},
            esl_decision="allow",
        )
        assert result == "Standard Outreach"
