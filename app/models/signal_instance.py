"""SignalInstance model — entity-level signals (Issue #189, Phase 2).

Populated by deriver engine from SignalEvents. Unique per (entity_id, signal_id, pack_id).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SignalInstance(Base):
    """Entity-level signal instance derived from SignalEvents.

    One row per (company, signal_id, pack). first_seen/last_seen track
    event time range for this signal at this entity.
    """

    __tablename__ = "signal_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    signal_id: Mapped[str] = mapped_column(String(100), nullable=False)
    pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_packs.id", ondelete="CASCADE"),
        nullable=False,
    )
    strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
