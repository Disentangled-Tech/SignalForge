"""ORE critic unit tests (Issue #124)."""

from __future__ import annotations

from app.services.ore.critic import check_critic


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
