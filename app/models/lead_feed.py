"""LeadFeed model — briefing projection (Phase 3, Issue #192).

One row per (workspace_id, entity_id, pack_id, as_of).
Populated by update_lead_feed stage after score.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.company import Company


class LeadFeed(Base):
    """Projection table for briefing emerging companies.

    Populated from ReadinessSnapshot + EngagementSnapshot after score stage.
    Briefing reads from lead_feed when populated; falls back to get_emerging_companies.
    """

    __tablename__ = "lead_feed"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "entity_id",
            "pack_id",
            "as_of",
            name="uq_lead_feed_workspace_entity_pack_as_of",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_packs.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    composite_score: Mapped[int] = mapped_column(Integer, nullable=False)
    top_reasons: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    esl_score: Mapped[float] = mapped_column(Float, nullable=False)
    engagement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    cadence_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stability_cap_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outreach_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    company: Mapped[Company] = relationship("Company", back_populates="lead_feed")
