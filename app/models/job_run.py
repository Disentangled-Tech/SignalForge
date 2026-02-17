"""JobRun model."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class JobRun(Base):
    """Records for internal job endpoints (/internal/scan, /internal/briefing)."""

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    company_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    companies_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    companies_analysis_changed: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # scan jobs: count of companies whose analysis changed (issue #61)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
