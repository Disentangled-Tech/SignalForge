"""Add lead_feed projection table (Phase 3, Issue #192).

Revision ID: 20260224_lead_feed
Revises: 20260224_signal_events_pack_idx
Create Date: 2026-02-24

Create lead_feed table for briefing projection.
Unique on (workspace_id, entity_id, pack_id, as_of).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260224_lead_feed"
down_revision: str | None = "20260224_signal_events_pack_idx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_feed",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("composite_score", sa.Integer(), nullable=False),
        sa.Column("top_reasons", postgresql.JSONB(), nullable=True),
        sa.Column("esl_score", sa.Float(), nullable=False),
        sa.Column("engagement_type", sa.String(length=64), nullable=False),
        sa.Column("cadence_blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("stability_cap_triggered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("outreach_score", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_lead_feed_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["companies.id"],
            name="fk_lead_feed_entity_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pack_id"],
            ["signal_packs.id"],
            name="fk_lead_feed_pack_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "entity_id",
            "pack_id",
            "as_of",
            name="uq_lead_feed_workspace_entity_pack_as_of",
        ),
    )
    op.create_index(
        "ix_lead_feed_workspace_as_of",
        "lead_feed",
        ["workspace_id", "as_of"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_lead_feed_workspace_as_of", table_name="lead_feed")
    op.drop_table("lead_feed")
