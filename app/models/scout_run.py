"""ScoutRun model — metadata for a single discovery scout run (Evidence-Only).

No FK to companies or signal_events. Per plan: scout runs are separate from the ingest→derive→score pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ScoutRun(Base):
    """Metadata for one LLM Discovery Scout run: timing, model, tokens, config snapshot."""

    __tablename__ = "scout_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_fetch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    config_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_bundles: Mapped[list["ScoutEvidenceBundle"]] = relationship(
        "ScoutEvidenceBundle",
        back_populates="scout_run",
        cascade="all, delete-orphan",
    )
