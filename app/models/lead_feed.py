"""LeadFeed model — projection table for lead list (Phase 1, Issue #225, ADR-004)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class LeadFeed(Base):
    """Projection row: one per (workspace_id, pack_id, entity_id).

    Replaces existing row on upsert. Populated from ReadinessSnapshot +
    EngagementSnapshot; updated incrementally on score and outreach events.
    """

    __tablename__ = "lead_feed"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_packs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    composite_score: Mapped[int] = mapped_column(Integer, nullable=False)
    top_signal_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    esl_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sensitivity_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outreach_status_summary: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
