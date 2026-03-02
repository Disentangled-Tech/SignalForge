"""Add index scout_runs (workspace_id, run_id) for list_bundles_by_run_for_workspace.

Revision ID: 20260302_scout_ws_run_idx
Revises: 20260238_scout_run_id_uuid
Create Date: 2026-03-02

Supports lookup by (run_id, workspace_id) in list_bundles_by_run_for_workspace.
Additive only; no schema break.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260302_scout_ws_run_idx"
down_revision: str | None = "20260238_scout_run_id_uuid"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_scout_runs_workspace_id_run_id",
        "scout_runs",
        ["workspace_id", "run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scout_runs_workspace_id_run_id",
        table_name="scout_runs",
    )
