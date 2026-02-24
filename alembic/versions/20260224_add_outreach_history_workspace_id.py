"""Add workspace_id to outreach_history for multi-tenant scoping (follow-up).

Revision ID: 20260224_outreach_workspace
Revises: 20260224_lead_feed_cols
Create Date: 2026-02-24

Adds nullable workspace_id to outreach_history. Backfills existing rows
to default workspace. Enables workspace-scoped outreach in lead_feed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260224_outreach_workspace"
down_revision: str | None = "20260224_lead_feed_cols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.add_column(
        "outreach_history",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Workspace that owns this outreach (multi-tenant)",
        ),
    )
    op.create_foreign_key(
        "fk_outreach_history_workspace_id",
        "outreach_history",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        sa.text(
            "UPDATE outreach_history SET workspace_id = CAST(:ws AS uuid) WHERE workspace_id IS NULL"
        ).bindparams(ws=DEFAULT_WORKSPACE_ID)
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_outreach_history_workspace_id",
        "outreach_history",
        type_="foreignkey",
    )
    op.drop_column("outreach_history", "workspace_id")
