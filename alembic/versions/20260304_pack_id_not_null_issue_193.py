"""pack_id NOT NULL on signal tables (Issue #193 M1).

Revision ID: 20260304_pack_id_not_null
Revises: 20260302_page_snapshots
Create Date: 2026-03-04

Backfills NULL pack_id to default pack (fractional_cto_v1) on signal_events,
readiness_snapshots, engagement_snapshots; then alters columns to NOT NULL.
Resolves default pack UUID from signal_packs at runtime so migration works
whether or not 20260223 inserted the canonical UUID.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260304_pack_id_not_null"
down_revision: str | None = "20260302_page_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT id FROM signal_packs WHERE pack_id = 'fractional_cto_v1' AND version = '1' LIMIT 1"
        )
    ).fetchone()
    if not row:
        raise RuntimeError(
            "Default pack (fractional_cto_v1, version 1) not found in signal_packs. "
            "Run earlier migrations (e.g. 20260223_signal_packs) first."
        )
    default_pack_uuid = str(row[0])

    for table in ["signal_events", "readiness_snapshots", "engagement_snapshots"]:
        op.execute(
            sa.text(
                f"UPDATE {table} SET pack_id = CAST(:pid AS uuid) WHERE pack_id IS NULL"
            ).bindparams(pid=default_pack_uuid)
        )
    for table in ["signal_events", "readiness_snapshots", "engagement_snapshots"]:
        op.alter_column(
            table,
            "pack_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=False,
        )
    # FK remains ON DELETE SET NULL; deleting a pack with referencing rows will fail with NotNullViolation.


def downgrade() -> None:
    for table in ["signal_events", "readiness_snapshots", "engagement_snapshots"]:
        op.alter_column(
            table,
            "pack_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=True,
        )
