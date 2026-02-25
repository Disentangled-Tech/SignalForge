"""AnalysisRecord model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.briefing_item import BriefingItem
    from app.models.company import Company


class AnalysisRecord(Base):
    """LLM analysis result for a company (stage classification + pain signals).

    pack_id attributes this analysis to a pack (Phase 2). NULL treated as default pack.
    """

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
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    pack_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_packs.id", ondelete="SET NULL"),
        nullable=True,
    )

    company: Mapped[Company] = relationship("Company", back_populates="analysis_records")
    briefing_items: Mapped[list[BriefingItem]] = relationship(
        "BriefingItem", back_populates="analysis", cascade="all, delete-orphan"
    )

