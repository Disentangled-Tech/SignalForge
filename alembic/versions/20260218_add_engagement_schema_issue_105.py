"""add engagement_snapshots, outcome to outreach_history, alignment columns (Issue #105)

Revision ID: 20260218_engagement
Revises: 20260218_outreach
Create Date: 2026-02-18

Engagement Suitability Layer (ESL) schema: engagement_snapshots, outreach outcome,
alignment flags on companies.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260218_engagement"
down_revision: str | None = "20260218_outreach"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create engagement_snapshots table
    op.create_table(
        "engagement_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("esl_score", sa.Float(), nullable=False),
        sa.Column("engagement_type", sa.String(length=64), nullable=False),
        sa.Column("stress_volatility_index", sa.Float(), nullable=True),
        sa.Column("communication_stability_index", sa.Float(), nullable=True),
        sa.Column("sustained_pressure_index", sa.Float(), nullable=True),
        sa.Column("cadence_blocked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("explain", postgresql.JSONB(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "as_of", name="uq_engagement_snapshots_company_as_of"),
    )
    op.create_index(
        "ix_engagement_snapshots_as_of_esl_score",
        "engagement_snapshots",
        ["as_of", "esl_score"],
        postgresql_ops={"esl_score": "DESC"},
    )

    # 2. Add outcome column to outreach_history
    op.add_column(
        "outreach_history",
        sa.Column("outcome", sa.String(length=64), nullable=True),
    )

    # 3. Add alignment columns to companies
    op.add_column(
        "companies",
        sa.Column("alignment_ok_to_contact", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("alignment_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "alignment_notes")
    op.drop_column("companies", "alignment_ok_to_contact")
    op.drop_column("outreach_history", "outcome")
    op.drop_index(
        "ix_engagement_snapshots_as_of_esl_score",
        table_name="engagement_snapshots",
        if_exists=True,
    )
    op.drop_table("engagement_snapshots", if_exists=True)
