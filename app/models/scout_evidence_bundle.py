"""ScoutEvidenceBundle model — one evidence bundle per candidate from a scout run.

No company_id FK. Per plan: scout output is evidence-only; no writes to companies or signal_events.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ScoutEvidenceBundle(Base):
    """One validated evidence bundle (candidate company + hypothesis + citations) from a scout run."""

    __tablename__ = "scout_evidence_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scout_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scout_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_website: Mapped[str] = mapped_column(String(2048), nullable=False)
    why_now_hypothesis: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)  # list of evidence items
    missing_information: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # list of strings
    raw_llm_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    scout_run: Mapped["ScoutRun"] = relationship(
        "ScoutRun",
        back_populates="evidence_bundles",
    )
