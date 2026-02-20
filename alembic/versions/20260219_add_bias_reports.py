"""add bias_reports table (Issue #112)

Revision ID: 20260219_bias_reports
Revises: 20260218_outreach_score
Create Date: 2026-02-19

Monthly bias audit job stores report results.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260219_bias_reports"
down_revision: Union[str, None] = "20260218_outreach_score"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bias_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_month", sa.Date(), nullable=False),
        sa.Column("surfaced_count", sa.Integer(), nullable=False),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bias_reports_report_month",
        "bias_reports",
        ["report_month"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_bias_reports_report_month", table_name="bias_reports")
    op.drop_table("bias_reports")
