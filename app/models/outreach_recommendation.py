"""OutreachRecommendation model — ORE output (Issue #124)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class OutreachRecommendation(Base):
    """ORE-generated outreach recommendation for a company."""

    __tablename__ = "outreach_recommendations"

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    company: Mapped["Company"] = relationship(
        "Company", back_populates="outreach_recommendations"
    )
