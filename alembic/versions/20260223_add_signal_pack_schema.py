"""Add signal_packs table and pack_id columns (Issue #189).

Revision ID: 20260223_signal_packs
Revises: 20260219_bias_reports
Create Date: 2026-02-23

Schema changes for pack-driven architecture:
- Create signal_packs table
- Insert fractional_cto_v1 pack
- Add pack_id to readiness_snapshots, engagement_snapshots, signal_events,
  signal_records, outreach_recommendations
- Backfill existing rows with fractional_cto_v1
- Add playbook_id to outreach_recommendations if missing
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260223_signal_packs"
down_revision: Union[str, None] = "20260219_bias_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FRACTIONAL_CTO_PACK_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def upgrade() -> None:
    # 1. Create signal_packs table
    op.create_table(
        "signal_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pack_id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_signal_packs_pack_id_version",
        "signal_packs",
        ["pack_id", "version"],
        unique=True,
    )

    # 2. Insert fractional_cto_v1 pack
    op.execute(
        f"""
        INSERT INTO signal_packs (id, pack_id, version, industry, description, is_active, created_at, updated_at)
        VALUES ('{FRACTIONAL_CTO_PACK_ID}'::uuid, 'fractional_cto_v1', '1', 'fractional_cto', 'Fractional CTO signal pack', true, now(), now())
        """
    )

    # 3. Add pack_id to tables (nullable first for backfill)
    for table in ["readiness_snapshots", "engagement_snapshots", "signal_events", "signal_records", "outreach_recommendations"]:
        op.add_column(
            table,
            sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_pack_id",
            table,
            "signal_packs",
            ["pack_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 4. Add playbook_id to outreach_recommendations if not exists
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("outreach_recommendations")]
    if "playbook_id" not in cols:
        op.add_column(
            "outreach_recommendations",
            sa.Column("playbook_id", sa.String(length=100), nullable=True),
        )

    # 5. Backfill existing rows with fractional_cto_v1
    for table in ["readiness_snapshots", "engagement_snapshots", "signal_events", "signal_records", "outreach_recommendations"]:
        op.execute(
            f"UPDATE {table} SET pack_id = '{FRACTIONAL_CTO_PACK_ID}'::uuid WHERE pack_id IS NULL"
        )

    # 6. Update unique constraints for readiness_snapshots and engagement_snapshots
    # Drop old (company_id, as_of), add (company_id, as_of, pack_id)
    op.drop_constraint("uq_readiness_snapshots_company_as_of", "readiness_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_readiness_snapshots_company_as_of_pack",
        "readiness_snapshots",
        ["company_id", "as_of", "pack_id"],
    )

    op.drop_constraint("uq_engagement_snapshots_company_as_of", "engagement_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_engagement_snapshots_company_as_of_pack",
        "engagement_snapshots",
        ["company_id", "as_of", "pack_id"],
    )


def downgrade() -> None:
    # Restore old unique constraints
    op.drop_constraint("uq_engagement_snapshots_company_as_of_pack", "engagement_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_engagement_snapshots_company_as_of",
        "engagement_snapshots",
        ["company_id", "as_of"],
    )

    op.drop_constraint("uq_readiness_snapshots_company_as_of_pack", "readiness_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_readiness_snapshots_company_as_of",
        "readiness_snapshots",
        ["company_id", "as_of"],
    )

    # Remove pack_id columns
    for table in ["readiness_snapshots", "engagement_snapshots", "signal_events", "signal_records", "outreach_recommendations"]:
        op.drop_constraint(f"fk_{table}_pack_id", table, type_="foreignkey")
        op.drop_column(table, "pack_id")

    # Remove playbook_id if we added it
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("outreach_recommendations")]
    if "playbook_id" in cols:
        op.drop_column("outreach_recommendations", "playbook_id")

    op.drop_index("ix_signal_packs_pack_id_version", table_name="signal_packs")
    op.drop_table("signal_packs")
