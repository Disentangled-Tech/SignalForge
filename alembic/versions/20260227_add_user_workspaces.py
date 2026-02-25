"""Add user_workspaces for workspace membership (Phase 3 access control).

Revision ID: 20260227_user_workspaces
Revises: 20260226_issue_240
Create Date: 2026-02-27

Creates user_workspaces (user_id, workspace_id) for workspace membership.
Backfills all existing users into default workspace.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260227_user_workspaces"
down_revision: str | None = "20260226_issue_240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "user_workspaces",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "workspace_id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_workspaces_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_user_workspaces_workspace_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_user_workspaces_workspace_id",
        "user_workspaces",
        ["workspace_id"],
        unique=False,
    )

    # Backfill: add all existing users to default workspace
    op.execute(
        sa.text(
            "INSERT INTO user_workspaces (user_id, workspace_id) "
            "SELECT u.id, CAST(:ws_id AS uuid) FROM users u "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM user_workspaces uw "
            "  WHERE uw.user_id = u.id AND uw.workspace_id = CAST(:ws_id AS uuid)"
            ")"
        ).bindparams(ws_id=DEFAULT_WORKSPACE_ID)
    )


def downgrade() -> None:
    op.drop_index("ix_user_workspaces_workspace_id", table_name="user_workspaces")
    op.drop_table("user_workspaces")
