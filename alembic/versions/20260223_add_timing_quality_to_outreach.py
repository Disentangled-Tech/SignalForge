"""add timing_quality_feedback to outreach_history (Issue #114)

Revision ID: 20260223_timing_quality
Revises: 20260219_bias_reports
Create Date: 2026-02-23

Track Outreach Outcomes: timing quality feedback for calibration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260223_timing_quality"
down_revision: Union[str, None] = "20260219_bias_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outreach_history",
        sa.Column("timing_quality_feedback", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outreach_history", "timing_quality_feedback")
