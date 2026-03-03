"""add_workspaces_and_signal_instances (Step 1.1, Issue #189).

Revision ID: ee6582573566
Revises: 20260223_signal_packs
Create Date: 2026-02-23

Add workspaces table (tenant) and signal_instances table per declarative pack plan.
- workspaces: default workspace with active_pack_id = fractional_cto_v1
- signal_instances: entity-level signals (populated when deriver engine runs)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ee6582573566"
down_revision: str | None = "20260223_signal_packs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FRACTIONAL_CTO_PACK_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # 1. Create workspaces table (tenant/workspace context)
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("active_pack_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["active_pack_id"],
            ["signal_packs.id"],
            name="fk_workspaces_active_pack_id",
            ondelete="SET NULL",
        ),
        if_not_exists=True,
    )

    # 2. Insert default workspace with active_pack_id = fractional_cto_v1 (idempotent)
    # Use pack from signal_packs (may differ from FRACTIONAL_CTO_PACK_ID if migrated elsewhere)
    op.execute(
        sa.text(
            "INSERT INTO workspaces (id, name, active_pack_id, created_at, updated_at) "
            "SELECT CAST(:id AS uuid), 'Default', sp.id, now(), now() "
            "FROM signal_packs sp "
            "WHERE sp.pack_id = 'fractional_cto_v1' AND sp.version = '1' "
            "AND NOT EXISTS (SELECT 1 FROM workspaces WHERE id = CAST(:id AS uuid))"
        ).bindparams(id=DEFAULT_WORKSPACE_ID)
    )

    # 3. Create signal_instances table (entity-level signals; populated when deriver runs)
    op.create_table(
        "signal_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.String(length=100), nullable=False),
        sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strength", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["companies.id"],
            name="fk_signal_instances_entity_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pack_id"],
            ["signal_packs.id"],
            name="fk_signal_instances_pack_id",
            ondelete="CASCADE",
        ),
        if_not_exists=True,
    )
    op.create_index(
        "ix_signal_instances_entity_pack",
        "signal_instances",
        ["entity_id", "pack_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_signal_instances_entity_pack",
        table_name="signal_instances",
        if_exists=True,
    )
    op.drop_table("signal_instances", if_exists=True)
    op.drop_table("workspaces", if_exists=True)
