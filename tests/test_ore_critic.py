"""ORE critic unit tests (Issue #124)."""

from __future__ import annotations

from app.services.ore.critic import RECOMMENDATION_ORDER, check_critic


def test_rejects_surveillance_phrase() -> None:
    """Draft with 'I noticed you' fails critic."""
    result = check_critic(
        "Quick question",
        "Hi Jane, I noticed you posted about hiring. Want me to send a checklist? No worries if now isn't the time.",
    )
    assert result.passed is False
    assert any("Surveillance" in v for v in result.violations)


def test_rejects_urgency_language() -> None:
    """Draft with 'ASAP' fails critic."""
    result = check_critic(
        "Urgent",
        "Please reply ASAP. No pressure if now isn't the time.",
    )
    assert result.passed is False
    assert any("Urgency" in v for v in result.violations)


def test_rejects_multiple_ctas() -> None:
    """Draft with multiple CTAs fails critic."""
    result = check_critic(
        "Quick question",
        "Want me to send it? Open to a 15-min chat? No worries if now isn't the time.",
    )
    assert result.passed is False
    assert any("Multiple CTAs" in v for v in result.violations)


def test_rejects_missing_opt_out() -> None:
    """Draft without opt-out language fails critic."""
    result = check_critic(
        "Quick question",
        "Hi Jane, teams often hit a complexity step-change. Want me to send a checklist?",
    )
    assert result.passed is False
    assert any("opt-out" in v.lower() for v in result.violations)


def test_passes_valid_draft() -> None:
    """Valid ORE draft passes critic."""
    result = check_critic(
        "Quick question about TestCo",
        "Hi Jane, teams often hit a complexity step-change when product and hiring accelerate. "
        "Want me to send a 2-page Tech Inflection Checklist? No worries if now isn't the time.",
    )
    assert result.passed is True
    assert len(result.violations) == 0


def test_rejects_pack_forbidden_phrase() -> None:
    """When forbidden_phrases is provided and draft contains a phrase, critic fails (Issue #176 M3)."""
    result = check_critic(
        "Quick question",
        "Hi Jane, we have a limited-time offer for you. Want me to send a checklist? No worries if now isn't the time.",
        forbidden_phrases=["limited-time offer"],
    )
    assert result.passed is False
    assert any("Pack forbidden phrase" in v for v in result.violations)
    assert any("limited-time offer" in v for v in result.violations)


def test_passes_when_forbidden_phrase_absent() -> None:
    """When forbidden_phrases is provided but draft does not contain any, critic can pass (other rules permitting)."""
    result = check_critic(
        "Quick question about TestCo",
        "Hi Jane, teams often hit a complexity step-change when product and hiring accelerate. "
        "Want me to send a 2-page Tech Inflection Checklist? No worries if now isn't the time.",
        forbidden_phrases=["limited-time offer", "act now"],
    )
    assert result.passed is True
    assert len(result.violations) == 0


def test_forbidden_phrases_none_or_empty_unchanged() -> None:
    """When forbidden_phrases is None or empty, only core rules apply (backward compat)."""
    draft_subject = "Quick question"
    draft_message = (
        "Hi Jane, teams often hit a complexity step-change. "
        "Want me to send a checklist? No worries if now isn't the time."
    )
    result_none = check_critic(draft_subject, draft_message, forbidden_phrases=None)
    result_empty = check_critic(draft_subject, draft_message, forbidden_phrases=[])
    assert result_none.passed is True
    assert result_empty.passed is True


# --- Issue #120 M2: critic context and suppressed-signal check ---


def test_critic_result_has_violation_details() -> None:
    """CriticResult includes violation_details for logging (M2)."""
    result = check_critic(
        "Quick question about TestCo",
        "Hi Jane, teams often hit a complexity step-change. "
        "Want me to send a 2-page Tech Inflection Checklist? No worries if now isn't the time.",
    )
    assert hasattr(result, "violation_details")
    assert isinstance(result.violation_details, list)
    assert len(result.violation_details) == 0


def test_suppressed_signal_ids_none_or_empty_no_extra_check() -> None:
    """When suppressed_signal_ids is None or empty, no suppressed-signal check (backward compat)."""
    draft_subject = "Quick question about TestCo"
    draft_message = (
        "Hi Jane, teams often hit a complexity step-change. "
        "Want me to send a 2-page Tech Inflection Checklist? No worries if now isn't the time."
    )
    result_none = check_critic(draft_subject, draft_message, suppressed_signal_ids=None)
    result_empty = check_critic(draft_subject, draft_message, suppressed_signal_ids=set())
    assert result_none.passed is True
    assert result_empty.passed is True
    assert result_none.violation_details == []
    assert result_empty.violation_details == []


def test_rejects_draft_mentioning_suppressed_signal_phrase() -> None:
    """When suppressed_signal_ids is set and draft contains a reference phrase, critic fails (M2)."""
    result = check_critic(
        "Quick question",
        "Hi Jane, I see you are struggling financially. Want me to send a checklist? No worries if now isn't the time.",
        suppressed_signal_ids={"financial_distress"},
    )
    assert result.passed is False
    assert any(
        "suppressed signal" in v.lower() or "financial" in v.lower() for v in result.violations
    )
    assert len(result.violation_details) >= 1
    detail = result.violation_details[0]
    assert detail.get("violation_type") == "suppressed_signal"
    assert detail.get("signal_id") == "financial_distress"
    assert "phrase" in detail


def test_passes_when_suppressed_signal_phrase_absent() -> None:
    """When suppressed_signal_ids is set but draft does not contain reference phrases, no violation (M2)."""
    result = check_critic(
        "Quick question about TestCo",
        "Hi Jane, teams often hit a complexity step-change when product and hiring accelerate. "
        "Want me to send a 2-page Tech Inflection Checklist? No worries if now isn't the time.",
        suppressed_signal_ids={"financial_distress"},
    )
    assert result.passed is True
    assert not any(d.get("violation_type") == "suppressed_signal" for d in result.violation_details)


def test_suppressed_signal_check_case_insensitive() -> None:
    """Suppressed-signal phrase check is case-insensitive (M2)."""
    result = check_critic(
        "Quick question",
        "Hi Jane, they are in DISTRESS. Want me to send a checklist? No worries if now isn't the time.",
        suppressed_signal_ids={"distress_mentioned"},
    )
    assert result.passed is False
    assert any(
        d.get("violation_type") == "suppressed_signal"
        and d.get("signal_id") == "distress_mentioned"
        for d in result.violation_details
    )


def test_optional_kwargs_pack_id_tone_allowed_labels_do_not_break() -> None:
    """Optional kwargs pack_id, tone_constraint, allowed_signal_labels accepted (M2; tone check in M4)."""
    result = check_critic(
        "Quick question about TestCo",
        "Hi Jane, teams often hit a complexity step-change. Want me to send a checklist? No worries if now isn't the time.",
        suppressed_signal_ids=None,
        tone_constraint="Soft Value Share",
        pack_id=None,
        allowed_signal_labels=None,
    )
    assert result.passed is True


def test_esl_gate_filter_uses_critic_recommendation_order() -> None:
    """ESL gate filter must use the same RECOMMENDATION_ORDER as critic (single source of truth)."""
    from app.services.esl.esl_gate_filter import RECOMMENDATION_ORDER as gate_order

    critic_order = RECOMMENDATION_ORDER
    assert gate_order is critic_order, (
        "esl_gate_filter must import RECOMMENDATION_ORDER from critic"
    )


def test_rejects_shame_framing() -> None:
    """Draft with core shame phrase fails critic (M4)."""
    result = check_critic(
        "Quick question",
        "Hi Jane, you're struggling with scale. Want me to send a checklist? No worries if now isn't the time.",
    )
    assert result.passed is False
    assert any("Shame" in v for v in result.violations)
    assert any(d.get("violation_type") == "shame_framing" for d in (result.violation_details or []))


def test_tone_tier_exceeded_fails_when_constraint_set() -> None:
    """When tone_constraint is Soft Value Share, draft suggesting Standard Outreach fails (M4)."""
    result = check_critic(
        "Quick question",
        "Hi Jane, want to schedule a 15-min call? No worries if now isn't the time.",
        tone_constraint="Soft Value Share",
    )
    assert result.passed is False
    assert any("Tone tier" in v for v in result.violations)
    assert any(d.get("violation_type") == "tone_tier" for d in (result.violation_details or []))
