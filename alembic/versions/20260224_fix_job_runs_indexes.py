"""Fix job_runs indexes: workspace-scoped idempotency, rate limit (Phase 1 fix).

Revision ID: 20260224_job_runs_indexes
Revises: 20260224_job_run_pipeline
Create Date: 2026-02-24

- Replace idempotency unique index with (workspace_id, idempotency_key) for
  multi-tenant isolation
- Add ix_job_runs_workspace_job_started for rate limit query performance
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260224_job_runs_indexes"
down_revision: str | None = "20260224_job_run_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_job_runs_idempotency_key", table_name="job_runs")

    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ix_job_runs_workspace_idempotency "
            "ON job_runs (workspace_id, idempotency_key) "
            "WHERE idempotency_key IS NOT NULL"
        )
    )

    op.create_index(
        "ix_job_runs_workspace_job_started",
        "job_runs",
        ["workspace_id", "job_type", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_runs_workspace_job_started", table_name="job_runs")
    op.drop_index("ix_job_runs_workspace_idempotency", table_name="job_runs")

    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ix_job_runs_idempotency_key "
            "ON job_runs (idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
    )
