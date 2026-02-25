"""Add missing columns to lead_feed when table exists with outdated schema.

Revision ID: 20260224_lead_feed_cols
Revises: 20260224_lead_feed
Create Date: 2026-02-24

Handles lead_feed tables created before full schema (e.g. top_signal_ids missing).
Adds columns only when missing; idempotent.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260224_lead_feed_cols"
down_revision: str | None = "20260224_lead_feed"
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

    if not _column_exists(conn, "lead_feed", "top_signal_ids"):
        op.add_column(
            "lead_feed",
            sa.Column("top_signal_ids", postgresql.JSONB(), nullable=True),
        )
    if not _column_exists(conn, "lead_feed", "esl_decision"):
        op.add_column(
            "lead_feed",
            sa.Column("esl_decision", sa.String(length=32), nullable=True),
        )
    if not _column_exists(conn, "lead_feed", "sensitivity_level"):
        op.add_column(
            "lead_feed",
            sa.Column("sensitivity_level", sa.String(length=32), nullable=True),
        )
    if not _column_exists(conn, "lead_feed", "last_seen"):
        op.add_column(
            "lead_feed",
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        )
    if not _column_exists(conn, "lead_feed", "outreach_status_summary"):
        op.add_column(
            "lead_feed",
            sa.Column("outreach_status_summary", postgresql.JSONB(), nullable=True),
        )
    if not _column_exists(conn, "lead_feed", "as_of"):
        op.add_column(
            "lead_feed",
            sa.Column("as_of", sa.Date(), nullable=True),
        )
    if not _column_exists(conn, "lead_feed", "updated_at"):
        op.add_column(
            "lead_feed",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            ),
        )

    # Legacy schema may have NOT NULL columns; make nullable for plan schema
    for col, col_type in [
        ("esl_score", sa.Float()),
        ("engagement_type", sa.String(64)),
    ]:
        if _column_exists(conn, "lead_feed", col):
            op.alter_column(
                "lead_feed",
                col,
                existing_type=col_type,
                nullable=True,
            )


def downgrade() -> None:
    # TODO(migration): Intentionally no-op. Columns may be in use; full rollback
    # requires downgrading to 20260224_lead_feed which drops the lead_feed table.
    pass
