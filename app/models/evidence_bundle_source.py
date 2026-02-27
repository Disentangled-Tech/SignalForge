"""EvidenceBundleSource ORM — join table linking evidence_bundles to evidence_sources (Issue #276)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EvidenceBundleSource(Base):
    """Association between an evidence bundle and a source (N:M via join table)."""

    __tablename__ = "evidence_bundle_sources"

    __table_args__ = (PrimaryKeyConstraint("bundle_id", "source_id"),)

    bundle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evidence_bundles.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evidence_sources.id", ondelete="CASCADE"),
        nullable=False,
    )

    bundle: Mapped["EvidenceBundle"] = relationship(
        "EvidenceBundle",
        back_populates="sources",
    )
    source: Mapped["EvidenceSource"] = relationship(
        "EvidenceSource",
        back_populates="bundle_assocs",
    )
