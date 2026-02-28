"""Add index on signal_events.pack_id for deriver query performance (maintainer review).

Revision ID: 20260224_signal_events_pack_idx
Revises: 20260224_signal_instances_unique
Create Date: 2026-02-24

Enables efficient pack-scoped queries in deriver engine.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260224_signal_events_pack_idx"
down_revision: str | None = "20260224_signal_instances_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_signal_events_pack_id",
        "signal_events",
        ["pack_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_signal_events_pack_id", table_name="signal_events")
