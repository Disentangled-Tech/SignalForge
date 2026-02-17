"""add_company_id_to_job_runs

Revision ID: e77e9209fe33
Revises: 26bb8c9d58d5
Create Date: 2026-02-17 13:16:50.361085

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e77e9209fe33'
down_revision: Union[str, None] = '26bb8c9d58d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_runs",
        sa.Column("company_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_job_runs_company_id",
        "job_runs",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_job_runs_company_id",
        "job_runs",
        ["company_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_runs_company_id", table_name="job_runs")
    op.drop_constraint("fk_job_runs_company_id", "job_runs", type_="foreignkey")
    op.drop_column("job_runs", "company_id")
