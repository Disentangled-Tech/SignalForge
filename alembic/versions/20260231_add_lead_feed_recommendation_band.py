"""Add recommendation_band to lead_feed (Issue #242 Phase 3).

Revision ID: 20260231_lead_feed_band
Revises: 20260230_config_checksum_bands
Create Date: 2026-02-31

Nullable column for pack recommendation band (IGNORE/WATCH/HIGH_PRIORITY).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260231_lead_feed_band"
down_revision: str | None = "20260230_config_checksum_bands"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(conn, table: str, column: str) -> bool:
    r = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c)"
        ),
        {"t": table, "c": column},
    ).scalar()
    return bool(r)


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'lead_feed')"
        )
    ).scalar():
        return

    if not _column_exists(conn, "lead_feed", "recommendation_band"):
        op.add_column(
            "lead_feed",
            sa.Column("recommendation_band", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if not conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'lead_feed')"
        )
    ).scalar():
        return

    if _column_exists(conn, "lead_feed", "recommendation_band"):
        op.drop_column("lead_feed", "recommendation_band")
