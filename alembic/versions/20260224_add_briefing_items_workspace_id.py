"""Add workspace_id to briefing_items for multi-tenant scoping (Issue #225).

Revision ID: 20260224_briefing_workspace
Revises: 20260224_outreach_workspace
Create Date: 2026-02-24

Adds nullable workspace_id to briefing_items. Backfills existing rows
to default workspace. Enables workspace-scoped briefing when multi-workspace enabled.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260224_briefing_workspace"
down_revision: str | None = "20260224_outreach_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.add_column(
        "briefing_items",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Workspace that owns this briefing (multi-tenant)",
        ),
    )
    op.create_foreign_key(
        "fk_briefing_items_workspace_id",
        "briefing_items",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        sa.text(
            "UPDATE briefing_items SET workspace_id = CAST(:ws AS uuid) WHERE workspace_id IS NULL"
        ).bindparams(ws=DEFAULT_WORKSPACE_ID)
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_briefing_items_workspace_id",
        "briefing_items",
        type_="foreignkey",
    )
    op.drop_column("briefing_items", "workspace_id")
