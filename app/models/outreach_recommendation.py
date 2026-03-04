"""OutreachRecommendation model — ORE output (Issue #124)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.company import Company


class OutreachRecommendation(Base):
    """ORE-generated outreach recommendation for a company."""

    __tablename__ = "outreach_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "as_of",
            "pack_id",
            name="uq_outreach_recommendations_company_as_of_pack",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    recommendation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    outreach_score: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    draft_variants: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    strategy_notes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    safeguards_triggered: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    generation_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pack_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_packs.id", ondelete="SET NULL"),
        nullable=True,
    )
    playbook_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    company: Mapped[Company] = relationship("Company", back_populates="outreach_recommendations")
