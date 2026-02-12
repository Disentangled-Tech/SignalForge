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

    # Database
    database_url: str = "postgresql://localhost:5432/signalforge_dev"

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

    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", self.app_name)
        self.debug = os.getenv("DEBUG", "false").lower() == "true"

        default_user = os.getenv("PGUSER") or os.getenv("USER") or "postgres"
        default_url = (
            f"postgresql://{default_user}:"
            f"{os.getenv('PGPASSWORD', '')}@"
            f"{os.getenv('PGHOST', 'localhost')}:"
            f"{os.getenv('PGPORT', '5432')}/"
            f"{os.getenv('PGDATABASE', 'signalforge_dev')}"
        )
        self.database_url = os.getenv("DATABASE_URL", default_url)

        self.secret_key = os.getenv("SECRET_KEY", "")
        self.internal_job_token = os.getenv("INTERNAL_JOB_TOKEN", "")

        self.llm_provider = os.getenv("LLM_PROVIDER", self.llm_provider)
        self.llm_api_key = os.getenv("LLM_API_KEY")
        self.llm_model = os.getenv("LLM_MODEL", self.llm_model)

        self.briefing_time = os.getenv("BRIEFING_TIME", self.briefing_time)
        self.briefing_email_enabled = os.getenv(
            "BRIEFING_EMAIL_ENABLED", "false"
        ).lower() == "true"
