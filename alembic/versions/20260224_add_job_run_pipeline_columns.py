"""Add job_run pipeline columns (Phase 1, Issue #192).

Revision ID: 20260224_job_run_pipeline
Revises: 20260224_config_checksum
Create Date: 2026-02-24

Add workspace_id, pack_id, retry_count, idempotency_key to job_runs.
Backfill existing rows with default workspace and fractional_cto_v1 pack.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260224_job_run_pipeline"
down_revision: str | None = "20260224_config_checksum"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.add_column(
        "job_runs",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "job_runs",
        sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "job_runs",
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "job_runs",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )

    op.create_foreign_key(
        "fk_job_runs_workspace_id",
        "job_runs",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_job_runs_pack_id",
        "job_runs",
        "signal_packs",
        ["pack_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Partial unique index: enforce uniqueness only when idempotency_key is set
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ix_job_runs_idempotency_key "
            "ON job_runs (idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
    )

    # Backfill: workspace_id = default workspace, pack_id = fractional_cto_v1
    op.execute(
        sa.text(
            "UPDATE job_runs SET workspace_id = CAST(:wid AS uuid) WHERE workspace_id IS NULL"
        ).bindparams(wid=DEFAULT_WORKSPACE_ID)
    )
    op.execute(
        sa.text(
            "UPDATE job_runs SET pack_id = sp.id FROM signal_packs sp "
            "WHERE sp.pack_id = 'fractional_cto_v1' AND sp.version = '1' "
            "AND job_runs.pack_id IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_job_runs_idempotency_key", table_name="job_runs")
    op.drop_constraint("fk_job_runs_pack_id", "job_runs", type_="foreignkey")
    op.drop_constraint("fk_job_runs_workspace_id", "job_runs", type_="foreignkey")
    op.drop_column("job_runs", "idempotency_key")
    op.drop_column("job_runs", "retry_count")
    op.drop_column("job_runs", "pack_id")
    op.drop_column("job_runs", "workspace_id")
