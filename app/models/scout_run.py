"""ScoutRun model — metadata for a single discovery scout run.

No FK to companies or signal_events. workspace_id scopes runs to a tenant;
any API that lists or filters scout runs must enforce workspace_id in queries.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.scout_evidence_bundle import ScoutEvidenceBundle


class ScoutRun(Base):
    """Metadata for one LLM discovery scout run (Evidence-Only mode).

    Stores run_id (UUID), timestamps, model version, token/latency counts,
    config snapshot (ICP, allowlist/denylist ref, query_count), status.
    workspace_id scopes the run to a tenant; any API exposing scout data must
    filter by workspace_id. No reference to companies or signal_events.
    """

    __tablename__ = "scout_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_fetch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # ICP, allowlist/denylist ref, query_count
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_bundles: Mapped[list[ScoutEvidenceBundle]] = relationship(
        "ScoutEvidenceBundle",
        back_populates="scout_run",
        cascade="all, delete-orphan",
        order_by="ScoutEvidenceBundle.id",
    )
