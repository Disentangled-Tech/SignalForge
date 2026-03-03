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
