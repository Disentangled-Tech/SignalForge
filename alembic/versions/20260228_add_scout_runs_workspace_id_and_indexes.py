"""Add workspace_id to scout_runs and indexes for list/filter (follow-up 1 & 5).

Revision ID: 20260228_scout_workspace
Revises: 20260228_merge_heads
Create Date: 2026-02-28

Adds workspace_id (nullable, FK to workspaces) for tenant scoping. Adds
indexes (workspace_id, started_at) and (workspace_id, status) for future
API list/filter by workspace. Additive only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260228_scout_workspace"
down_revision: str | None = "20260228_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scout_runs",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_scout_runs_workspace_id_workspaces",
        "scout_runs",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_scout_runs_workspace_id",
        "scout_runs",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_scout_runs_workspace_started",
        "scout_runs",
        ["workspace_id", "started_at"],
        unique=False,
        postgresql_ops={"started_at": "DESC"},
    )
    op.create_index(
        "ix_scout_runs_workspace_status",
        "scout_runs",
        ["workspace_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scout_runs_workspace_status",
        table_name="scout_runs",
    )
    op.drop_index(
        "ix_scout_runs_workspace_started",
        table_name="scout_runs",
    )
    op.drop_index(
        "ix_scout_runs_workspace_id",
        table_name="scout_runs",
    )
    op.drop_constraint(
        "fk_scout_runs_workspace_id_workspaces",
        "scout_runs",
        type_="foreignkey",
    )
    op.drop_column("scout_runs", "workspace_id")
