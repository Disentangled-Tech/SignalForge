"""add domain column and company_aliases table (Issue #88)

Revision ID: 20260218_aliases
Revises: 20260218_ore
Create Date: 2026-02-18

Add domain column to companies for entity resolution.
Add company_aliases table for alias tracking (name, domain, url, social).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260218_aliases"
down_revision: str | None = "20260218_ore"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("domain", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_companies_domain",
        "companies",
        ["domain"],
        unique=True,
        postgresql_where=sa.text("domain IS NOT NULL"),
    )

    op.create_table(
        "company_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("alias_type", sa.String(length=32), nullable=False),
        sa.Column("alias_value", sa.String(length=512), nullable=False),
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
        "ix_company_aliases_type_value",
        "company_aliases",
        ["alias_type", "alias_value"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_aliases_type_value",
        table_name="company_aliases",
        if_exists=True,
    )
    op.drop_table("company_aliases", if_exists=True)
    op.drop_index(
        "ix_companies_domain",
        table_name="companies",
        if_exists=True,
    )
    op.drop_column("companies", "domain")
