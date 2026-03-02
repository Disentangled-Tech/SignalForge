"""Add evidence_bundle_id to signal_events (Watchlist Seeder M1, Issue #279).

Revision ID: 20260302_evidence_bundle_id
Revises: 20260302_scout_ws_run_idx
Create Date: 2026-03-02

Nullable FK to evidence_bundles.id; no backfill. Enables Watchlist Seeder to
persist Core Events with originating bundle reference.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260302_evidence_bundle_id"
down_revision: str | None = "20260302_scout_ws_run_idx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signal_events",
        sa.Column(
            "evidence_bundle_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_signal_events_evidence_bundle_id",
        "signal_events",
        "evidence_bundles",
        ["evidence_bundle_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_signal_events_evidence_bundle_id",
        "signal_events",
        type_="foreignkey",
    )
    op.drop_column("signal_events", "evidence_bundle_id")
