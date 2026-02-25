"""Add index on user_workspaces (user_id) for access checks (Phase 3).

Revision ID: 20260229_user_workspaces_user_idx
Revises: 20260228_analysis_pack_idx
Create Date: 2026-02-29

Optimizes user_has_access_to_workspace and "list workspaces for user" queries.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260229_user_ws_user_idx"
down_revision: str | None = "20260228_analysis_pack_idx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_user_workspaces_user_id",
        "user_workspaces",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_workspaces_user_id", table_name="user_workspaces")
