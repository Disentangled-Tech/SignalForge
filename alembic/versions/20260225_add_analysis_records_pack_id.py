"""Add pack_id to analysis_records (Phase 2, Plan Step 2).

Revision ID: 20260225_analysis_pack_id
Revises: 20260224_briefing_workspace
Create Date: 2026-02-25

Adds nullable pack_id to analysis_records for pack attribution.
No backfill in migration; NULL treated as default pack in reads.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260225_analysis_pack_id"
down_revision: str | None = "20260224_briefing_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_records",
        sa.Column(
            "pack_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Pack this analysis was produced with (Phase 2)",
        ),
    )
    op.create_foreign_key(
        "fk_analysis_records_pack_id",
        "analysis_records",
        "signal_packs",
        ["pack_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_analysis_records_pack_id",
        "analysis_records",
        type_="foreignkey",
    )
    op.drop_column("analysis_records", "pack_id")
