"""BiasReport model (Issue #112). Per-pack key (report_month, pack_id) (Issue #193)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BiasReport(Base):
    """Monthly bias audit report (Issue #112). Keyed by (report_month, pack_id)."""

    __tablename__ = "bias_reports"

    __table_args__ = (
        UniqueConstraint(
            "report_month",
            "pack_id",
            name="uq_bias_reports_report_month_pack_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_month: Mapped[date] = mapped_column(Date, nullable=False)
    pack_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_packs.id", ondelete="SET NULL"),
        nullable=True,
    )
    surfaced_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
