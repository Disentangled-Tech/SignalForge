"""Add ix_lead_feed_workspace_pack_as_of index (Phase 3 follow-up).

Revision ID: 20260224_lead_feed_idx
Revises: 20260224_lead_feed
Create Date: 2026-02-24

Optimizes briefing query: filter by (workspace_id, pack_id, as_of).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260224_lead_feed_idx"
down_revision: str | None = "20260224_lead_feed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_lead_feed_workspace_pack_as_of",
        "lead_feed",
        ["workspace_id", "pack_id", "as_of"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lead_feed_workspace_pack_as_of",
        table_name="lead_feed",
    )
