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
- Add indexes on (as_of, pack_id) for readiness_snapshots and engagement_snapshots

Downgrade limitation:
  Downgrade fails when multiple packs have data. Restoring UNIQUE(company_id, as_of)
  would conflict with duplicate rows. Run pre-downgrade check before downgrading.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260223_signal_packs"
down_revision: str | None = "20260219_bias_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
    )
    op.create_index(
        "ix_signal_packs_pack_id_version",
        "signal_packs",
        ["pack_id", "version"],
        unique=True,
    )

    # 2. Insert fractional_cto_v1 pack (parameterized to avoid injection)
    op.execute(
        sa.text(
            "INSERT INTO signal_packs (id, pack_id, version, industry, description, is_active, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), 'fractional_cto_v1', '1', 'fractional_cto', 'Fractional CTO signal pack', true, now(), now())"
        ).bindparams(id=FRACTIONAL_CTO_PACK_ID)
    )

    # 3. Add pack_id to tables (nullable first for backfill)
    for table in [
        "readiness_snapshots",
        "engagement_snapshots",
        "signal_events",
        "signal_records",
        "outreach_recommendations",
    ]:
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

    # 5. Backfill existing rows with fractional_cto_v1 (parameterized)
    for table in [
        "readiness_snapshots",
        "engagement_snapshots",
        "signal_events",
        "signal_records",
        "outreach_recommendations",
    ]:
        op.execute(
            sa.text(
                f"UPDATE {table} SET pack_id = CAST(:pid AS uuid) WHERE pack_id IS NULL"
            ).bindparams(pid=FRACTIONAL_CTO_PACK_ID)
        )

    # 6. Update unique constraints for readiness_snapshots and engagement_snapshots
    # Drop old (company_id, as_of), add (company_id, as_of, pack_id)
    op.drop_constraint(
        "uq_readiness_snapshots_company_as_of", "readiness_snapshots", type_="unique"
    )
    op.create_unique_constraint(
        "uq_readiness_snapshots_company_as_of_pack",
        "readiness_snapshots",
        ["company_id", "as_of", "pack_id"],
    )

    op.drop_constraint(
        "uq_engagement_snapshots_company_as_of", "engagement_snapshots", type_="unique"
    )
    op.create_unique_constraint(
        "uq_engagement_snapshots_company_as_of_pack",
        "engagement_snapshots",
        ["company_id", "as_of", "pack_id"],
    )

    # 7. Add indexes for pack-scoped queries (as_of, pack_id)
    op.create_index(
        "ix_readiness_snapshots_as_of_pack_id",
        "readiness_snapshots",
        ["as_of", "pack_id"],
        unique=False,
    )
    op.create_index(
        "ix_engagement_snapshots_as_of_pack_id",
        "engagement_snapshots",
        ["as_of", "pack_id"],
        unique=False,
    )


def downgrade() -> None:
    # Pre-check: abort if multiple packs have data (would violate UNIQUE(company_id, as_of))
    conn = op.get_bind()
    for table in ["readiness_snapshots", "engagement_snapshots"]:
        dup = conn.execute(
            sa.text(
                f"SELECT company_id, as_of FROM {table} "
                "GROUP BY company_id, as_of HAVING COUNT(*) > 1"
            )
        ).fetchall()
        if dup:
            raise RuntimeError(
                f"Cannot downgrade: {table} has duplicate (company_id, as_of) across packs. "
                f"Found {len(dup)} conflicts. Consolidate or delete multi-pack data first."
            )

    # Drop indexes before dropping constraints
    op.drop_index("ix_readiness_snapshots_as_of_pack_id", table_name="readiness_snapshots")
    op.drop_index("ix_engagement_snapshots_as_of_pack_id", table_name="engagement_snapshots")

    # Restore old unique constraints
    op.drop_constraint(
        "uq_engagement_snapshots_company_as_of_pack", "engagement_snapshots", type_="unique"
    )
    op.create_unique_constraint(
        "uq_engagement_snapshots_company_as_of",
        "engagement_snapshots",
        ["company_id", "as_of"],
    )

    op.drop_constraint(
        "uq_readiness_snapshots_company_as_of_pack", "readiness_snapshots", type_="unique"
    )
    op.create_unique_constraint(
        "uq_readiness_snapshots_company_as_of",
        "readiness_snapshots",
        ["company_id", "as_of"],
    )

    # Remove pack_id columns
    for table in [
        "readiness_snapshots",
        "engagement_snapshots",
        "signal_events",
        "signal_records",
        "outreach_recommendations",
    ]:
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
