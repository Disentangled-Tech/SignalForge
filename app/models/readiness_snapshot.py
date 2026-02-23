"""ReadinessSnapshot model — daily readiness scoring outputs (v2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ReadinessSnapshot(Base):
    """Daily readiness score snapshot for a company (v2 readiness engine)."""

    __tablename__ = "readiness_snapshots"

    __table_args__ = (
        UniqueConstraint("company_id", "as_of", name="uq_readiness_snapshots_company_as_of"),
        Index("ix_readiness_snapshots_as_of_composite", "as_of", "composite", postgresql_ops={"composite": "DESC"}),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    momentum: Mapped[int] = mapped_column(Integer, nullable=False)
    complexity: Mapped[int] = mapped_column(Integer, nullable=False)
    pressure: Mapped[int] = mapped_column(Integer, nullable=False)
    leadership_gap: Mapped[int] = mapped_column(Integer, nullable=False)
    composite: Mapped[int] = mapped_column(Integer, nullable=False)
    explain: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pack_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_packs.id", ondelete="SET NULL"),
        nullable=True,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    company: Mapped["Company"] = relationship("Company", back_populates="readiness_snapshots")
