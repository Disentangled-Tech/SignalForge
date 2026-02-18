"""EngagementSnapshot model — daily ESL scores per company (Issue #105)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
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
    engagement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    stress_volatility_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    communication_stability_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    sustained_pressure_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    cadence_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    explain: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    company: Mapped["Company"] = relationship(
        "Company", back_populates="engagement_snapshots"
    )
