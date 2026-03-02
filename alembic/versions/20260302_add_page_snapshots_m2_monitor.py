"""Add page_snapshots table (M2 Diff-Based Monitor Engine).

Revision ID: 20260302_page_snapshots
Revises: 20260302_evidence_bundle_id
Create Date: 2026-03-02

Append-only snapshot store keyed by (company_id, url); latest by fetched_at
used for diff detection. Pack-agnostic; no pack_id.
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
        sa.Column(
            "company_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_page_snapshots_company_url_fetched",
        "page_snapshots",
        ["company_id", "url", "fetched_at"],
        unique=False,
        postgresql_ops={"fetched_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_page_snapshots_company_url_fetched",
        table_name="page_snapshots",
    )
    op.drop_table("page_snapshots")
