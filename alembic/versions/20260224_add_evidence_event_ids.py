"""Add evidence_event_ids to signal_instances (Phase 2, Issue #173).

Revision ID: 20260224_evidence_event_ids
Revises: 20260224_lead_feed_idx
Create Date: 2026-02-24

Add nullable JSONB column for SignalEvent IDs that contributed to each
SignalInstance. No backfill; new rows populated going forward.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260224_evidence_event_ids"
down_revision: str | None = "20260224_signal_events_pack_idx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signal_instances",
        sa.Column(
            "evidence_event_ids",
            postgresql.JSONB(),
            nullable=True,
            comment="SignalEvent IDs that contributed to this instance (Phase 2, Issue #173)",
        ),
    )


def downgrade() -> None:
    op.drop_column("signal_instances", "evidence_event_ids")
