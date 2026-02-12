"""BriefingItem model."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class BriefingItem(Base):
    """Daily briefing entry with outreach draft for a company."""

    __tablename__ = "briefing_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    analysis_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analysis_records.id", ondelete="CASCADE"), nullable=False
    )
    why_now: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_angle: Mapped[str | None] = mapped_column(Text, nullable=True)
    outreach_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outreach_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    briefing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    company: Mapped["Company"] = relationship("Company", back_populates="briefing_items")
    analysis: Mapped["AnalysisRecord"] = relationship(
        "AnalysisRecord", back_populates="briefing_items"
    )

