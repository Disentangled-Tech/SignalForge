"""Add pack_id to bias_reports; key by (report_month, pack_id) (Issue #193).

Revision ID: 20260306_bias_reports_pack
Revises: 20260305_ore_unique
Create Date: 2026-03-06

- Adds pack_id (UUID, FK signal_packs.id, nullable).
- Backfills existing rows with default pack (fractional_cto_v1) when present.
- Drops unique on report_month; adds unique (report_month, pack_id).
Enables per-pack bias reports and prevents cross-workspace overwrite.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260306_bias_reports_pack"
down_revision: str | None = "20260305_ore_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bias_reports",
        sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_bias_reports_pack_id",
        "bias_reports",
        "signal_packs",
        ["pack_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Backfill: set pack_id to default pack (fractional_cto_v1) where it exists
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE bias_reports br
            SET pack_id = (SELECT id FROM signal_packs
                           WHERE pack_id = 'fractional_cto_v1' AND version = '1'
                           LIMIT 1)
            WHERE br.pack_id IS NULL
            """
        )
    )

    op.drop_index("ix_bias_reports_report_month", table_name="bias_reports")
    op.create_unique_constraint(
        "uq_bias_reports_report_month_pack_id",
        "bias_reports",
        ["report_month", "pack_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_bias_reports_report_month_pack_id",
        "bias_reports",
        type_="unique",
    )
    op.create_index(
        "ix_bias_reports_report_month",
        "bias_reports",
        ["report_month"],
        unique=True,
    )
    op.drop_constraint("fk_bias_reports_pack_id", "bias_reports", type_="foreignkey")
    op.drop_column("bias_reports", "pack_id")
