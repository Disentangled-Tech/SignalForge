"""Email delivery service for daily briefings."""

from __future__ import annotations

import html
import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings

logger = logging.getLogger(__name__)


def _build_html_email(briefing_items: list, failure_summary: str | None = None) -> str:
    """Build an HTML email body from briefing items (issue #32: optional failure_summary)."""
    rows = ""
    for item in briefing_items:
        company = getattr(item, "company", None)
        company_name = getattr(company, "name", "Unknown") if company else "Unknown"
        stage = getattr(company, "current_stage", "—") if company else "—"
        score = getattr(company, "cto_need_score", "—") if company else "—"
        why_now = getattr(item, "why_now", "") or ""
        risk = getattr(item, "risk_summary", "") or ""
        subject = getattr(item, "outreach_subject", "") or ""
        message = getattr(item, "outreach_message", "") or ""

        rows += (
            "<tr>"
            f'<td style="padding:8px;border:1px solid #ddd;font-weight:bold">{company_name}</td>'
            f'<td style="padding:8px;border:1px solid #ddd">{stage}</td>'
            f'<td style="padding:8px;border:1px solid #ddd;text-align:center">{score}</td>'
            "</tr>"
            "<tr>"
            f'<td colspan="3" style="padding:8px;border:1px solid #ddd">'
            f"<strong>Why now:</strong> {why_now}<br>"
            f"<strong>Risk:</strong> {risk}<br>"
            f"<strong>Outreach subject:</strong> {subject}<br>"
            f"<strong>Message:</strong><br>{message}"
            "</td>"
            "</tr>"
        )

    failure_section = ""
    if failure_summary:
        escaped = html.escape(failure_summary)
        failure_section = (
            f'<h3 style="color:#dc2626;margin-top:1.5rem;">Some companies could not be processed</h3>'
            f'<pre style="background:#fef2f2;padding:1rem;border-radius:6px;font-size:0.85rem;overflow-x:auto;">{escaped}</pre>'
        )

    table_section = ""
    if rows:
        table_section = (
            '<table style="border-collapse:collapse;width:100%">'
            "<tr>"
            '<th style="padding:8px;border:1px solid #ddd;text-align:left">Company</th>'
            '<th style="padding:8px;border:1px solid #ddd;text-align:left">Stage</th>'
            '<th style="padding:8px;border:1px solid #ddd;text-align:center">CTO Score</th>'
            "</tr>"
            f"{rows}"
            "</table>"
        )
    elif failure_summary:
        table_section = "<p>No briefing items were generated.</p>"
    else:
        table_section = (
            '<table style="border-collapse:collapse;width:100%">'
            "<tr>"
            '<th style="padding:8px;border:1px solid #ddd;text-align:left">Company</th>'
            '<th style="padding:8px;border:1px solid #ddd;text-align:left">Stage</th>'
            '<th style="padding:8px;border:1px solid #ddd;text-align:center">CTO Score</th>'
            "</tr></table>"
        )

    return (
        "<html><body>"
        f"<h2>SignalForge Daily Briefing &mdash; {date.today()}</h2>"
        f"{table_section}"
        f"{failure_section}"
        "</body></html>"
    )


def _build_text_email(briefing_items: list, failure_summary: str | None = None) -> str:
    """Build a plain-text email body from briefing items (issue #32: optional failure_summary)."""
    lines = [f"SignalForge Daily Briefing - {date.today()}", "=" * 40, ""]
    if not briefing_items and failure_summary:
        lines.append("No briefing items were generated.")
        lines.append("")
    for item in briefing_items:
        company = getattr(item, "company", None)
        company_name = getattr(company, "name", "Unknown") if company else "Unknown"
        stage = getattr(company, "current_stage", "—") if company else "—"
        score = getattr(company, "cto_need_score", "—") if company else "—"

        lines.append(f"Company: {company_name}")
        lines.append(f"  Stage: {stage}  |  CTO Score: {score}")
        lines.append(f"  Why now: {getattr(item, 'why_now', '') or ''}")
        lines.append(f"  Risk: {getattr(item, 'risk_summary', '') or ''}")
        lines.append(f"  Outreach subject: {getattr(item, 'outreach_subject', '') or ''}")
        lines.append(f"  Message: {getattr(item, 'outreach_message', '') or ''}")
        lines.append("-" * 40)
        lines.append("")
    if failure_summary:
        lines.append("")
        lines.append("--- Some companies could not be processed ---")
        lines.append(failure_summary)
    return "\n".join(lines)


def send_briefing_email(
    briefing_items: list,
    recipient: str,
    settings=None,
    *,
    failure_summary: str | None = None,
) -> bool:
    """Send the daily briefing email (issue #32: optional failure_summary).

    When briefing_items is empty and failure_summary is set, sends a failure-only
    notification email to alert the operator.

    Returns True on success, False on any failure.
    """
    if settings is None:
        settings = get_settings()

    if not recipient:
        logger.warning("email_send_skipped: no recipient configured")
        return False

    smtp_host = getattr(settings, "smtp_host", "")
    if not smtp_host:
        logger.warning("email_send_skipped: SMTP host not configured")
        return False

    if briefing_items:
        subject = f"SignalForge Daily Briefing - {date.today()}"
    else:
        subject = f"SignalForge Briefing — Failures (no items generated) - {date.today()}"

    html_body = _build_html_email(briefing_items, failure_summary)
    text_body = _build_text_email(briefing_items, failure_summary)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = getattr(settings, "smtp_from", "")
    msg["To"] = recipient
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, getattr(settings, "smtp_port", 587)) as server:
            server.starttls()
            smtp_user = getattr(settings, "smtp_user", "")
            smtp_password = getattr(settings, "smtp_password", "")
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.sendmail(msg["From"], [recipient], msg.as_string())
        logger.info("email_sent: recipient=%s items=%d", recipient, len(briefing_items))
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("email_auth_failed: could not authenticate with SMTP server")
        return False
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("email_send_failed: %s", exc)
        return False

