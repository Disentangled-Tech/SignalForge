"""EngagementSnapshot model — daily ESL scores per company (Issue #105)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EngagementSnapshot(Base):
    """Daily engagement suitability score snapshot for a company (ESL)."""

    __tablename__ = "engagement_snapshots"

    __table_args__ = (
        UniqueConstraint("company_id", "as_of", name="uq_engagement_snapshots_company_as_of"),
        Index(
            "ix_engagement_snapshots_as_of_esl_score",
            "as_of",
            "esl_score",
            postgresql_ops={"esl_score": "DESC"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    esl_score: Mapped[float] = mapped_column(Float, nullable=False)
    outreach_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # round(TRS × ESL), Issue #103
    engagement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    stress_volatility_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    communication_stability_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    sustained_pressure_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    cadence_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    explain: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pack_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_packs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # ESL decision gate (Phase 4, Issue #175): allow | allow_with_constraints | suppress
    esl_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    esl_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sensitivity_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    company: Mapped[Company] = relationship(
        "Company", back_populates="engagement_snapshots"
    )
