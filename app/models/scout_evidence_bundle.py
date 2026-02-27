"""ScoutEvidenceBundle model — one Evidence Bundle per candidate from a scout run.

FK to scout_runs only. No company_id or signal_events. Per plan: additive only;
stores candidate_company_name, company_website, why_now_hypothesis, evidence (JSONB),
missing_information (JSONB), raw_llm_output (JSONB).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.scout_run import ScoutRun


class ScoutEvidenceBundle(Base):
    """One structured Evidence Bundle (one candidate) from a scout run.

    evidence and missing_information match EvidenceBundle schema (list of
    EvidenceItem dicts and list of strings). raw_llm_output stores full LLM
    response for audit. No company_id FK — scout does not create companies.
    """

    __tablename__ = "scout_evidence_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scout_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scout_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_company_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    company_website: Mapped[str] = mapped_column(String(2048), nullable=False)
    why_now_hypothesis: Mapped[str] = mapped_column(
        String(2000), default="", nullable=False
    )
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )  # list of EvidenceItem-like dicts
    missing_information: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    # Sensitive: full LLM response; apply same access control and audit as other
    # LLM/audit fields when exposing via API (see docs/discovery_scout.md).
    raw_llm_output: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    scout_run: Mapped[ScoutRun] = relationship(
        "ScoutRun", back_populates="evidence_bundles"
    )
