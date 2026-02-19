"""add outreach_score to engagement_snapshots (Issue #103)

Revision ID: 20260218_outreach_score
Revises: 20260218_aliases
Create Date: 2026-02-18

Persist OutreachScore = round(TRS × ESL) for query/audit.
Uses Python round() for backfill to match compute_outreach_score() (banker's rounding).
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text
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
    # Backfill using Python round() to match compute_outreach_score() (banker's rounding).
    # PostgreSQL ROUND() uses round-half-away-from-zero; Python uses round-half-to-even.
    conn = op.get_bind()
    rows = conn.execute(
        text("""
            SELECT es.id, rs.composite, es.esl_score
            FROM engagement_snapshots es
            JOIN readiness_snapshots rs
              ON rs.company_id = es.company_id AND rs.as_of = es.as_of
        """)
    ).fetchall()
    for row in rows:
        outreach_score = round(row.composite * row.esl_score)
        conn.execute(
            text("UPDATE engagement_snapshots SET outreach_score = :score WHERE id = :id"),
            {"score": outreach_score, "id": row.id},
        )


def downgrade() -> None:
    op.drop_column("engagement_snapshots", "outreach_score")
