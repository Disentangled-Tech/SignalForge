"""add readiness_snapshots table (Issue #82)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-18

Stores daily readiness scoring outputs for v2 readiness engine.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "readiness_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("momentum", sa.Integer(), nullable=False),
        sa.Column("complexity", sa.Integer(), nullable=False),
        sa.Column("pressure", sa.Integer(), nullable=False),
        sa.Column("leadership_gap", sa.Integer(), nullable=False),
        sa.Column("composite", sa.Integer(), nullable=False),
        sa.Column("explain", postgresql.JSONB(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "as_of", name="uq_readiness_snapshots_company_as_of"
        ),
    )
    op.create_index(
        "ix_readiness_snapshots_as_of_composite",
        "readiness_snapshots",
        ["as_of", "composite"],
        postgresql_ops={"composite": "DESC"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_readiness_snapshots_as_of_composite",
        table_name="readiness_snapshots",
        if_exists=True,
    )
    op.drop_table("readiness_snapshots", if_exists=True)
