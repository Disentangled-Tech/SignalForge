"""AnalysisRecord model."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AnalysisRecord(Base):
    """LLM analysis result for a company (stage classification + pain signals)."""

    __tablename__ = "analysis_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pain_signals_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_bullets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    company: Mapped["Company"] = relationship("Company", back_populates="analysis_records")
    briefing_items: Mapped[list["BriefingItem"]] = relationship(
        "BriefingItem", back_populates="analysis", cascade="all, delete-orphan"
    )

