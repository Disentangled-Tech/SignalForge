"""EvidenceSource ORM — deduplicated source (url, content_hash) for evidence (Issue #276)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EvidenceSource(Base):
    """One evidence source (url, snippet, content_hash); deduplicated by (content_hash, url)."""

    __tablename__ = "evidence_sources"

    __table_args__ = (
        UniqueConstraint(
            "content_hash",
            "url",
            name="uq_evidence_sources_content_hash_url",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    bundle_assocs: Mapped[list["EvidenceBundleSource"]] = relationship(
        "EvidenceBundleSource",
        back_populates="source",
        cascade="all, delete-orphan",
    )
