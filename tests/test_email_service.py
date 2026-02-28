"""Tests for the email briefing service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.email_service import (
    _build_html_email,
    _build_text_email,
    send_briefing_email,
)


def _make_item(
    company_name: str = "Acme Corp",
    stage: str = "Series A",
    score: int = 8,
    why_now: str = "Hiring CTO",
    risk: str = "Low runway",
    subject: str = "Let's connect",
    message: str = "Hi, I noticed you're hiring…",
) -> SimpleNamespace:
    """Create a mock briefing item with a nested company."""
    company = SimpleNamespace(
        name=company_name,
        current_stage=stage,
        cto_need_score=score,
    )
    return SimpleNamespace(
        company=company,
        why_now=why_now,
        risk_summary=risk,
        outreach_subject=subject,
        outreach_message=message,
    )


def _make_settings(**overrides) -> SimpleNamespace:
    """Create mock settings with SMTP defaults."""
    from tests.test_constants import TEST_SMTP_PASSWORD

    defaults = dict(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password=TEST_SMTP_PASSWORD,
        smtp_from="noreply@example.com",
        briefing_email_to="boss@example.com",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ── HTML builder ──────────────────────────────────────────────


def test_build_html_email_contains_company_names() -> None:
    items = [_make_item("AlphaCo"), _make_item("BetaCo")]
    html = _build_html_email(items)
    assert "AlphaCo" in html
    assert "BetaCo" in html


def test_build_html_email_contains_html_tags() -> None:
    html = _build_html_email([_make_item()])
    assert "<html>" in html
    assert "<table" in html
    assert "</html>" in html


def test_build_html_email_contains_briefing_fields() -> None:
    html = _build_html_email([_make_item(why_now="Expanding team", risk="Burn rate")])
    assert "Expanding team" in html
    assert "Burn rate" in html


def test_build_html_email_empty_list() -> None:
    html = _build_html_email([])
    assert "<html>" in html
    assert "<table" in html


def test_build_html_email_includes_failure_summary() -> None:
    """When failure_summary provided, it appears in HTML (issue #32)."""
    html = _build_html_email([_make_item()], failure_summary="Company 1 (Acme): LLM failed")
    assert "Some companies could not be processed" in html
    assert "Company 1 (Acme): LLM failed" in html


def test_build_text_email_includes_failure_summary() -> None:
    """When failure_summary provided, it appears in text body (issue #32)."""
    text = _build_text_email([_make_item()], failure_summary="Company 2 (Beta): timeout")
    assert "Some companies could not be processed" in text
    assert "Company 2 (Beta): timeout" in text


# ── Text builder ─────────────────────────────────────────────


def test_build_text_email_readable() -> None:
    text = _build_text_email([_make_item("GammaCo")])
    assert "GammaCo" in text
    assert "SignalForge Daily Briefing" in text


def test_build_text_email_contains_fields() -> None:
    text = _build_text_email([_make_item(subject="Hello", message="Body text")])
    assert "Hello" in text
    assert "Body text" in text


def test_build_text_email_empty_list() -> None:
    text = _build_text_email([])
    assert "SignalForge Daily Briefing" in text


# ── send_briefing_email ─────────────────────────────────────


@patch("app.services.email_service.smtplib.SMTP")
def test_send_email_success(mock_smtp_cls: MagicMock) -> None:
    from tests.test_constants import TEST_SMTP_PASSWORD

    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    items = [_make_item()]
    settings = _make_settings()
    result = send_briefing_email(items, "dest@example.com", settings=settings)

    assert result is True
    mock_smtp_cls.assert_called_once_with("smtp.example.com", 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user@example.com", TEST_SMTP_PASSWORD)
    mock_server.sendmail.assert_called_once()


@patch("app.services.email_service.smtplib.SMTP")
def test_send_email_connection_error(mock_smtp_cls: MagicMock) -> None:
    mock_smtp_cls.side_effect = OSError("Connection refused")
    result = send_briefing_email([_make_item()], "dest@example.com", settings=_make_settings())
    assert result is False


def test_send_email_empty_recipient() -> None:
    result = send_briefing_email([_make_item()], "", settings=_make_settings())
    assert result is False


def test_send_email_smtp_not_configured() -> None:
    settings = _make_settings(smtp_host="")
    result = send_briefing_email([_make_item()], "dest@example.com", settings=settings)
    assert result is False


@patch("app.services.email_service.smtplib.SMTP")
def test_send_email_auth_failure(mock_smtp_cls: MagicMock) -> None:
    import smtplib as _smtplib

    mock_server = MagicMock()
    mock_server.login.side_effect = _smtplib.SMTPAuthenticationError(535, b"Bad credentials")
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = send_briefing_email([_make_item()], "dest@example.com", settings=_make_settings())
    assert result is False


@patch("app.services.email_service.smtplib.SMTP")
def test_send_email_partial_failures_subject(mock_smtp_cls: MagicMock) -> None:
    """When items exist but failure_summary is set, subject indicates partial failures."""
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    items = [_make_item("Acme")]
    result = send_briefing_email(
        items,
        "dest@example.com",
        settings=_make_settings(),
        failure_summary="Company 2 (Beta): LLM timeout",
    )

    assert result is True
    mock_server.sendmail.assert_called_once()
    sent_msg = mock_server.sendmail.call_args[0][2]
    # Subject is MIME-encoded; "Partial Failures" appears as Partial_Failures in q-encoding
    assert "Partial_Failures" in sent_msg or "Partial Failures" in sent_msg
