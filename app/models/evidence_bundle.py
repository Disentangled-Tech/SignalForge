"""EvidenceBundle ORM — immutable evidence bundle from Scout (Issue #276).

Append-only; no updated_at. Versioned against core taxonomy and derivers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EvidenceBundle(Base):
    """One immutable evidence bundle from a Scout run; versioned for core taxonomy/derivers."""

    __tablename__ = "evidence_bundles"

    __table_args__ = (
        Index(
            "ix_evidence_bundles_core_versions",
            "core_taxonomy_version",
            "core_derivers_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    scout_version: Mapped[str] = mapped_column(String(128), nullable=False)
    core_taxonomy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    core_derivers_version: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("signal_packs.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_model_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    structured_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    sources: Mapped[list["EvidenceBundleSource"]] = relationship(
        "EvidenceBundleSource",
        back_populates="bundle",
        cascade="all, delete-orphan",
    )
    claims: Mapped[list["EvidenceClaim"]] = relationship(
        "EvidenceClaim",
        back_populates="bundle",
        cascade="all, delete-orphan",
    )
