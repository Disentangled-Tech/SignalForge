"""add outreach_score to engagement_snapshots (Issue #103)

Revision ID: 20260218_outreach_score
Revises: 20260218_aliases
Create Date: 2026-02-18

Persist OutreachScore = round(TRS × ESL) for query/audit.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260218_outreach_score"
down_revision: Union[str, None] = "20260218_aliases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "engagement_snapshots",
        sa.Column("outreach_score", sa.Integer(), nullable=True),
    )
    # Backfill from readiness_snapshots join: outreach_score = round(composite * esl_score)
    op.execute("""
        UPDATE engagement_snapshots es
        SET outreach_score = ROUND(rs.composite * es.esl_score)
        FROM readiness_snapshots rs
        WHERE rs.company_id = es.company_id AND rs.as_of = es.as_of
    """)


def downgrade() -> None:
    op.drop_column("engagement_snapshots", "outreach_score")
