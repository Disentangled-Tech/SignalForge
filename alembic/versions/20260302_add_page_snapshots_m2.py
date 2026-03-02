"""Add page_snapshots table (Diff-Based Monitor M2, Issue #280).

Revision ID: 20260302_page_snapshots
Revises: 20260302_evidence_bundle_id
Create Date: 2026-03-02

One row per (company_id, url); updated on each fetch (latest wins).
Used by monitor for diff detection; pack-agnostic.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260302_page_snapshots"
down_revision: str | None = "20260302_evidence_bundle_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "page_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_page_snapshots_company_id_url",
        "page_snapshots",
        ["company_id", "url"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_page_snapshots_company_id_url",
        table_name="page_snapshots",
        if_exists=True,
    )
    op.drop_table("page_snapshots", if_exists=True)
