"""ScoutEvidenceBundle ORM — one evidence bundle per candidate from a scout run.

No company_id FK. Per plan Step 4.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ScoutEvidenceBundle(Base):
    """One evidence bundle (candidate + hypothesis + evidence) from a scout run."""

    __tablename__ = "scout_evidence_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scout_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("scout_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_website: Mapped[str] = mapped_column(String(2048), nullable=False)
    why_now_hypothesis: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    evidence: Mapped[dict | list] = mapped_column(JSONB, nullable=False)
    missing_information: Mapped[dict | list] = mapped_column(JSONB, default=list, nullable=False)
    raw_llm_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    scout_run: Mapped["ScoutRun"] = relationship("ScoutRun", back_populates="bundles")
