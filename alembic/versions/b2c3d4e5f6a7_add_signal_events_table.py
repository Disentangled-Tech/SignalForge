"""add signal_events table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-18

Normalized event store for readiness signals (Issue #81).
Supports future ingestion adapters and v2 scoring engine.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_event_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_time", sa.DateTime(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_signal_events_company_event_time",
        "signal_events",
        ["company_id", "event_time"],
        postgresql_ops={"event_time": "DESC"},
    )
    op.create_index(
        "ix_signal_events_event_type_event_time",
        "signal_events",
        ["event_type", "event_time"],
        postgresql_ops={"event_time": "DESC"},
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_signal_events_source_source_event_id "
        "ON signal_events (source, source_event_id) "
        "WHERE source_event_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_signal_events_source_source_event_id")
    op.drop_index("ix_signal_events_event_type_event_time", table_name="signal_events")
    op.drop_index("ix_signal_events_company_event_time", table_name="signal_events")
    op.drop_table("signal_events")
