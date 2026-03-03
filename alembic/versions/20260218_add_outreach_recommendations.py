"""add outreach_recommendations table (Issue #124)

Revision ID: 20260218_ore
Revises: 20260218_outreach
Create Date: 2026-02-18

ORE output: company_id, as_of, recommendation_type, outreach_score,
channel, draft_variants (JSONB), strategy_notes (JSONB),
safeguards_triggered (JSONB).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260218_ore"
down_revision: str | None = "20260218_engagement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outreach_recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("recommendation_type", sa.String(length=64), nullable=False),
        sa.Column("outreach_score", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=True),
        sa.Column("draft_variants", postgresql.JSONB(), nullable=True),
        sa.Column("strategy_notes", postgresql.JSONB(), nullable=True),
        sa.Column("safeguards_triggered", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_outreach_recommendations_company_as_of",
        "outreach_recommendations",
        ["company_id", "as_of"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outreach_recommendations_company_as_of",
        table_name="outreach_recommendations",
        if_exists=True,
    )
    op.drop_table("outreach_recommendations", if_exists=True)
