"""
Application configuration. Loads from environment variables.
Secrets and sensitive config must never be hardcoded.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


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

    # LLM — Anthropic (Claude) only. Role env vars use Claude model names.
    llm_provider: str = "anthropic"
    llm_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None  # ANTHROPIC_API_KEY or fallback to llm_api_key
    llm_model: str = "claude-3-5-haiku-20241022"
    # Model roles (issue #15): reasoning=analysis, json=cheap, outreach=conversational
    llm_model_reasoning: str = "claude-sonnet-4-20250514"
    llm_model_json: str = "claude-3-5-haiku-20241022"
    llm_model_outreach: str = "claude-3-5-haiku-20241022"
    llm_model_scout: str = (
        "claude-sonnet-4-20250514"  # discovery scout evidence extraction (issue #275)
    )
    llm_timeout: float = 60.0
    llm_max_retries: int = 3

    # Pipeline (Phase 1, Issue #192) — per-workspace rate limit for /internal/* jobs.
    # 0 = disabled. Default 10 (Phase 3) limits each workspace to 10 jobs/hour per job_type.
    # Set WORKSPACE_JOB_RATE_LIMIT_PER_HOUR=0 to disable (e.g. for tests or heavy cron).
    workspace_job_rate_limit_per_hour: int = 10

    # Multi-workspace (Issue #225): when True, briefing/review scope by workspace_id
    multi_workspace_enabled: bool = False

    # Alerts (Issue #92, v2-spec §13)
    alert_delta_threshold: int = 15  # readiness_jump when |delta| >= this

    # Readiness (Issue #93, v2-spec §13)
    readiness_threshold: int = 60  # composite >= this for Emerging Companies section

    # Outreach (Issue #102) — Emerging Companies section
    outreach_score_threshold: int = 30  # min OutreachScore (TRS × ESL) to show
    weekly_review_limit: int = 5  # max companies in Emerging section (ORE spec: 3–5/week)

    # Briefing
    briefing_time: str = "08:00"  # 24h format for cron
    briefing_email_enabled: bool = False
    briefing_frequency: str = "daily"  # daily or weekly (issue #29)
    briefing_day_of_week: int = 0  # 0=Monday .. 6=Sunday

    # SMTP / Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    briefing_email_to: str = ""

    # Scout (LLM Discovery) — source allowlist/denylist; empty allowlist = all allowed
    scout_source_allowlist: list[str] = ()  # e.g. ["example.com", "news.ycombinator.com"]
    scout_source_denylist: list[str] = ()  # denylist takes precedence; e.g. ["blocked.com"]
    # M4 (Issue #277): when True, run Extractor per bundle and pass structured_payloads to store
    scout_run_extractor: bool = False
    # M3 (Issue #278): when True, run Verification Gate before store; failed bundles quarantined
    scout_verification_gate_enabled: bool = False
    # M4 (Issue #281): when True (and scout_run_extractor True), run LLM interpretation per bundle then extract with raw_extraction
    scout_run_interpretation: bool = False

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
        if raw_url.startswith("postgresql://") and not raw_url.startswith("postgresql+psycopg"):
            raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
        self.database_url = raw_url
        self.db_connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", str(self.db_connect_timeout)))

        self.secret_key = os.getenv("SECRET_KEY", "")
        self.internal_job_token = os.getenv("INTERNAL_JOB_TOKEN", "")

        raw_provider = os.getenv("LLM_PROVIDER", self.llm_provider)
        # ADR-012: Anthropic only. Coerce legacy/typo values so briefing and LLM flows don't fail.
        if raw_provider and str(raw_provider).strip().lower() != "anthropic":
            logger.warning(
                "LLM_PROVIDER=%r is not supported; using 'anthropic'. Set LLM_PROVIDER=anthropic in .env.",
                raw_provider,
            )
            self.llm_provider = "anthropic"
        else:
            self.llm_provider = "anthropic"
        self.llm_api_key = os.getenv("LLM_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or self.llm_api_key
        self.llm_model = os.getenv("LLM_MODEL", self.llm_model)
        # Role-specific models; legacy: LLM_MODEL used for all if role vars unset
        legacy_model = os.getenv("LLM_MODEL")
        self.llm_model_reasoning = (
            os.getenv("LLM_MODEL_REASONING") or legacy_model or self.llm_model_reasoning
        )
        self.llm_model_json = os.getenv("LLM_MODEL_JSON") or legacy_model or self.llm_model_json
        self.llm_model_outreach = (
            os.getenv("LLM_MODEL_OUTREACH") or legacy_model or self.llm_model_outreach
        )
        self.llm_model_scout = os.getenv("LLM_MODEL_SCOUT") or legacy_model or self.llm_model_scout
        self.llm_timeout = float(os.getenv("LLM_TIMEOUT", str(self.llm_timeout)))
        self.llm_max_retries = int(os.getenv("LLM_MAX_RETRIES", str(self.llm_max_retries)))

        self.workspace_job_rate_limit_per_hour = int(
            os.getenv(
                "WORKSPACE_JOB_RATE_LIMIT_PER_HOUR",
                str(self.workspace_job_rate_limit_per_hour),
            )
        )
        self.multi_workspace_enabled = (
            os.getenv("MULTI_WORKSPACE_ENABLED", "false").lower() == "true"
        )
        self.alert_delta_threshold = int(
            os.getenv("ALERT_DELTA_THRESHOLD", str(self.alert_delta_threshold))
        )
        self.readiness_threshold = int(
            os.getenv("READINESS_THRESHOLD", str(self.readiness_threshold))
        )
        self.outreach_score_threshold = int(
            os.getenv("OUTREACH_SCORE_THRESHOLD", str(self.outreach_score_threshold))
        )
        self.weekly_review_limit = int(
            os.getenv("WEEKLY_REVIEW_LIMIT", str(self.weekly_review_limit))
        )

        self.briefing_time = os.getenv("BRIEFING_TIME", self.briefing_time)
        self.briefing_email_enabled = os.getenv("BRIEFING_EMAIL_ENABLED", "false").lower() == "true"
        self.briefing_frequency = os.getenv("BRIEFING_FREQUENCY", self.briefing_frequency).lower()
        self.briefing_day_of_week = int(
            os.getenv("BRIEFING_DAY_OF_WEEK", str(self.briefing_day_of_week))
        )

        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("SMTP_FROM", "")
        self.briefing_email_to = os.getenv("BRIEFING_EMAIL_TO", "")

        # Scout: comma-separated domains; empty = no restriction (allowlist) or none blocked (denylist)
        _allow = os.getenv("SCOUT_SOURCE_ALLOWLIST", "").strip()
        self.scout_source_allowlist = [s.strip().lower() for s in _allow.split(",") if s.strip()]
        _deny = os.getenv("SCOUT_SOURCE_DENYLIST", "").strip()
        self.scout_source_denylist = [s.strip().lower() for s in _deny.split(",") if s.strip()]
        _run_ext = os.getenv("SCOUT_RUN_EXTRACTOR", "0").strip().lower()
        self.scout_run_extractor = _run_ext in ("1", "true", "yes")
        _verif = os.getenv("SCOUT_VERIFICATION_GATE_ENABLED", "0").strip().lower()
        self.scout_verification_gate_enabled = _verif in ("1", "true", "yes")
        _interp = os.getenv("SCOUT_RUN_INTERPRETATION", "0").strip().lower()
        self.scout_run_interpretation = _interp in ("1", "true", "yes")
