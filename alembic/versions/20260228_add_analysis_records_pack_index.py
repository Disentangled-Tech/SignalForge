"""Add index on analysis_records (company_id, pack_id, created_at) for pack-scoped queries.

Revision ID: 20260228_analysis_pack_idx
Revises: 20260227_user_workspaces
Create Date: 2026-02-28

Optimizes pack-scoped analysis queries (company_detail, briefing _generate_for_company).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260228_analysis_pack_idx"
down_revision: str | None = "20260227_user_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_analysis_records_company_pack_created",
        "analysis_records",
        ["company_id", "pack_id", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_records_company_pack_created",
        table_name="analysis_records",
    )
