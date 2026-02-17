"""Settings resolver — merges AppSettings (DB) over env for operator-configurable values.

Issue #29: briefing_time, briefing_email, briefing_email_enabled, briefing_frequency,
briefing_day_of_week are resolved from AppSettings when set, else from environment.
SMTP and API keys remain env-only for security.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import get_settings
from app.services.settings_service import get_app_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# HH:MM format (24h)
_BRIEFING_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_VALID_FREQUENCIES = frozenset({"daily", "weekly"})


@dataclass
class ResolvedSettings:
    """Resolved operator settings: DB overrides env for briefing-related keys."""

    briefing_time: str
    briefing_email: str
    briefing_email_enabled: bool
    briefing_frequency: str
    briefing_day_of_week: int  # 0=Monday, 6=Sunday
    # Env-only (passed through for email service)
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str

    @property
    def briefing_email_recipient(self) -> str:
        """Email address to send briefing to. DB overrides env."""
        return self.briefing_email

    def should_send_briefing_email(self) -> bool:
        """True if briefing email should be sent (enabled + recipient + SMTP host)."""
        return (
            self.briefing_email_enabled
            and bool(self.briefing_email_recipient.strip())
            and bool(self.smtp_host.strip())
        )


def _parse_briefing_time(value: str | None) -> str | None:
    """Validate HH:MM format. Returns value if valid, else None."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    if _BRIEFING_TIME_RE.match(v):
        return v
    return None


def _parse_briefing_frequency(value: str | None) -> str:
    """Return 'daily' or 'weekly'. Invalid/missing -> 'daily'."""
    if not value or not isinstance(value, str):
        return "daily"
    v = value.strip().lower()
    return v if v in _VALID_FREQUENCIES else "daily"


def _parse_briefing_day_of_week(value: str | None) -> int:
    """Parse 0-6 (0=Monday). Invalid -> 0."""
    if value is None:
        return 0
    try:
        n = int(value)
        if 0 <= n <= 6:
            return n
    except (ValueError, TypeError):
        pass
    return 0


def _parse_bool(value: str | None) -> bool:
    """Parse 'true'/'1'/'yes' as True, else False."""
    if not value:
        return False
    return str(value).strip().lower() in ("true", "1", "yes")


def get_resolved_settings(db: Session) -> ResolvedSettings:
    """Merge AppSettings over env for operator-configurable briefing settings.

    DB values take precedence when present and valid. SMTP/API keys stay env-only.
    """
    env = get_settings()
    app = get_app_settings(db)

    # briefing_time: HH:MM
    db_time = _parse_briefing_time(app.get("briefing_time"))
    briefing_time = db_time if db_time else (env.briefing_time or "08:00")

    # briefing_email: recipient address
    db_email = app.get("briefing_email")
    if db_email is not None:
        briefing_email = str(db_email).strip()
    else:
        briefing_email = env.briefing_email_to or ""

    # briefing_email_enabled
    db_enabled = app.get("briefing_email_enabled")
    if db_enabled is not None:
        briefing_email_enabled = _parse_bool(str(db_enabled))
    else:
        briefing_email_enabled = env.briefing_email_enabled

    # briefing_frequency
    db_freq = app.get("briefing_frequency")
    if db_freq:
        briefing_frequency = _parse_briefing_frequency(db_freq)
    else:
        briefing_frequency = _parse_briefing_frequency(
            getattr(env, "briefing_frequency", None)
        ) or "daily"

    # briefing_day_of_week (0=Monday)
    db_day = app.get("briefing_day_of_week")
    if db_day is not None:
        briefing_day_of_week = _parse_briefing_day_of_week(db_day)
    else:
        briefing_day_of_week = getattr(env, "briefing_day_of_week", 0)
        if not isinstance(briefing_day_of_week, int):
            briefing_day_of_week = _parse_briefing_day_of_week(
                str(briefing_day_of_week)
            )

    return ResolvedSettings(
        briefing_time=briefing_time,
        briefing_email=briefing_email,
        briefing_email_enabled=briefing_email_enabled,
        briefing_frequency=briefing_frequency,
        briefing_day_of_week=briefing_day_of_week,
        smtp_host=env.smtp_host or "",
        smtp_port=env.smtp_port,
        smtp_user=env.smtp_user or "",
        smtp_password=env.smtp_password or "",
        smtp_from=env.smtp_from or "",
    )
