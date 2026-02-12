"""
Application configuration. Loads from environment variables.
Secrets and sensitive config must never be hardcoded.
"""

import os

from dotenv import load_dotenv

load_dotenv()
from functools import lru_cache
from typing import Optional


@lru_cache(maxsize=1)
def get_settings() -> "Settings":
    """Return cached settings instance."""
    return Settings()


class Settings:
    """Application settings loaded from environment."""

    # App
    app_name: str = "SignalForge"
    debug: bool = False

    # Database (postgresql+psycopg for psycopg3; use postgresql:// for psycopg2)
    database_url: str = "postgresql+psycopg://localhost:5432/signalforge_dev"
    db_connect_timeout: int = 10  # seconds

    # Security
    secret_key: str = ""
    internal_job_token: str = ""  # Required for /internal/* endpoints

    # LLM
    llm_provider: str = "openai"
    llm_api_key: Optional[str] = None
    llm_model: str = "gpt-4o-mini"

    # Briefing
    briefing_time: str = "08:00"  # 24h format for cron
    briefing_email_enabled: bool = False

    # SMTP / Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    briefing_email_to: str = ""

    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", self.app_name)
        self.debug = os.getenv("DEBUG", "false").lower() == "true"

        default_user = os.getenv("PGUSER") or os.getenv("USER") or "postgres"
        default_url = (
            f"postgresql+psycopg://{default_user}:"
            f"{os.getenv('PGPASSWORD', '')}@"
            f"{os.getenv('PGHOST', 'localhost')}:"
            f"{os.getenv('PGPORT', '5432')}/"
            f"{os.getenv('PGDATABASE', 'signalforge_dev')}"
        )
        raw_url = os.getenv("DATABASE_URL", default_url)
        # Ensure psycopg3 driver if URL uses generic postgresql://
        if raw_url.startswith("postgresql://") and not raw_url.startswith(
            "postgresql+psycopg"
        ):
            raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
        self.database_url = raw_url
        self.db_connect_timeout = int(
            os.getenv("DB_CONNECT_TIMEOUT", str(self.db_connect_timeout))
        )

        self.secret_key = os.getenv("SECRET_KEY", "")
        self.internal_job_token = os.getenv("INTERNAL_JOB_TOKEN", "")

        self.llm_provider = os.getenv("LLM_PROVIDER", self.llm_provider)
        self.llm_api_key = os.getenv("LLM_API_KEY")
        self.llm_model = os.getenv("LLM_MODEL", self.llm_model)

        self.briefing_time = os.getenv("BRIEFING_TIME", self.briefing_time)
        self.briefing_email_enabled = os.getenv(
            "BRIEFING_EMAIL_ENABLED", "false"
        ).lower() == "true"

        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("SMTP_FROM", "")
        self.briefing_email_to = os.getenv("BRIEFING_EMAIL_TO", "")
