"""JobRun model."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
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
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    companies_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    companies_esl_suppressed: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # score jobs: count with esl_decision=suppress (Phase 4, Issue #175)
    companies_analysis_changed: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # scan jobs: count of companies whose analysis changed (issue #61)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Pipeline columns (Phase 1, Issue #192)
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    pack_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("signal_packs.id", ondelete="SET NULL"),
        nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
