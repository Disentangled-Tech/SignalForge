"""Add lead_feed projection table (Phase 1, Issue #225, ADR-004).

Revision ID: 20260224_lead_feed
Revises: 20260224_bookkeeping_pack
Create Date: 2026-02-24

Creates lead_feed table for incremental projection from ReadinessSnapshot +
EngagementSnapshot. Unique per (workspace_id, pack_id, entity_id); replace on upsert.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260224_lead_feed"
down_revision: str | None = "20260224_bookkeeping_pack"
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


def _table_exists(conn) -> bool:
    """Check if lead_feed exists (pg_tables for reliability across schemas)."""
    r = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_tables "
            "WHERE schemaname = 'public' AND tablename = 'lead_feed')"
        )
    ).scalar()
    return bool(r)


def upgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn):
        # Idempotent: add missing columns when table exists with outdated schema
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
        # Ensure indices exist
        from sqlalchemy import inspect

        inspector = inspect(conn)
        idx_names = [idx["name"] for idx in inspector.get_indexes("lead_feed")]
        if "ix_lead_feed_workspace_pack_composite" not in idx_names:
            op.create_index(
                "ix_lead_feed_workspace_pack_composite",
                "lead_feed",
                ["workspace_id", "pack_id", "composite_score"],
                unique=False,
                postgresql_ops={"composite_score": "DESC"},
            )
        if "ix_lead_feed_workspace_pack_last_seen" not in idx_names:
            op.create_index(
                "ix_lead_feed_workspace_pack_last_seen",
                "lead_feed",
                ["workspace_id", "pack_id", "last_seen"],
                unique=False,
                postgresql_ops={"last_seen": "DESC"},
            )
        return
    try:
        op.create_table(
            "lead_feed",
            sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("composite_score", sa.Integer(), nullable=False),
            sa.Column("top_signal_ids", postgresql.JSONB(), nullable=True),
            sa.Column("esl_decision", sa.String(length=32), nullable=True),
            sa.Column("sensitivity_level", sa.String(length=32), nullable=True),
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
            sa.Column("outreach_status_summary", postgresql.JSONB(), nullable=True),
            sa.Column("as_of", sa.Date(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["workspace_id"],
                ["workspaces.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["pack_id"],
                ["signal_packs.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["entity_id"],
                ["companies.id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "workspace_id",
                "pack_id",
                "entity_id",
                name="uq_lead_feed_workspace_pack_entity",
            ),
        )
        op.create_index(
            "ix_lead_feed_workspace_pack_composite",
            "lead_feed",
            ["workspace_id", "pack_id", "composite_score"],
            unique=False,
            postgresql_ops={"composite_score": "DESC"},
        )
        op.create_index(
            "ix_lead_feed_workspace_pack_last_seen",
            "lead_feed",
            ["workspace_id", "pack_id", "last_seen"],
            unique=False,
            postgresql_ops={"last_seen": "DESC"},
        )
    except sa.exc.ProgrammingError as e:
        if "already exists" not in str(e).lower():
            raise
        # Table created outside migration; ensure schema is complete
        if _table_exists(conn):
            if not _column_exists(conn, "lead_feed", "top_signal_ids"):
                op.add_column(
                    "lead_feed",
                    sa.Column("top_signal_ids", postgresql.JSONB(), nullable=True),
                )
            # Indices may be missing
            from sqlalchemy import inspect

            inspector = inspect(conn)
            idx_names = [idx["name"] for idx in inspector.get_indexes("lead_feed")]
            if "ix_lead_feed_workspace_pack_composite" not in idx_names:
                op.create_index(
                    "ix_lead_feed_workspace_pack_composite",
                    "lead_feed",
                    ["workspace_id", "pack_id", "composite_score"],
                    unique=False,
                    postgresql_ops={"composite_score": "DESC"},
                )
            if "ix_lead_feed_workspace_pack_last_seen" not in idx_names:
                op.create_index(
                    "ix_lead_feed_workspace_pack_last_seen",
                    "lead_feed",
                    ["workspace_id", "pack_id", "last_seen"],
                    unique=False,
                    postgresql_ops={"last_seen": "DESC"},
                )


def downgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn):
        return
    op.drop_index(
        "ix_lead_feed_workspace_pack_last_seen",
        table_name="lead_feed",
        if_exists=True,
    )
    op.drop_index(
        "ix_lead_feed_workspace_pack_composite",
        table_name="lead_feed",
        if_exists=True,
    )
    op.drop_table("lead_feed")
