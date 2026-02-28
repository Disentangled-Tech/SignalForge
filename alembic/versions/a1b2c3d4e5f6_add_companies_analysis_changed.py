"""add companies_analysis_changed to job_runs

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-02-17

Tracks how many companies had analysis changes during scan-all runs (issue #61).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_runs",
        sa.Column("companies_analysis_changed", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_runs", "companies_analysis_changed")
