"""Fix scout_evidence_bundles.scout_run_id to UUID FK to scout_runs.run_id.

Revision ID: 20260238_scout_bundle_run_uuid
Revises: 20260236_evidence_store
Create Date: 2026-02-28

The 20260228_scout_runs migration created scout_run_id as Integer (FK to scout_runs.id).
The ORM and application expect UUID (FK to scout_runs.run_id). This migration alters
the column so model and DB match. Idempotent: no-op if column is already UUID.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260238_scout_bundle_run_uuid"
down_revision: str | None = "20260236_evidence_store"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    # Check if scout_run_id is already UUID (e.g. from another branch)
    r = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'scout_evidence_bundles' "
            "AND column_name = 'scout_run_id'"
        )
    )
    row = r.fetchone()
    if row and row[0] == "uuid":
        return

    # Drop existing FK (references scout_runs.id)
    op.drop_constraint(
        "scout_evidence_bundles_scout_run_id_fkey",
        "scout_evidence_bundles",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_scout_evidence_bundles_scout_run_id",
        table_name="scout_evidence_bundles",
    )
    # Add temp UUID column, backfill from scout_runs.run_id
    op.add_column(
        "scout_evidence_bundles",
        sa.Column("scout_run_id_uuid", postgresql.UUID(as_uuid=True), nullable=True),
    )
    conn.execute(
        sa.text(
            "UPDATE scout_evidence_bundles sb SET scout_run_id_uuid = sr.run_id "
            "FROM scout_runs sr WHERE sr.id = sb.scout_run_id"
        )
    )
    op.drop_column("scout_evidence_bundles", "scout_run_id")
    op.alter_column(
        "scout_evidence_bundles",
        "scout_run_id_uuid",
        new_column_name="scout_run_id",
        nullable=False,
    )
    op.create_foreign_key(
        "scout_evidence_bundles_scout_run_id_fkey",
        "scout_evidence_bundles",
        "scout_runs",
        ["scout_run_id"],
        ["run_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_scout_evidence_bundles_scout_run_id",
        "scout_evidence_bundles",
        ["scout_run_id"],
        unique=False,
    )


def downgrade() -> None:
    conn = op.get_bind()
    r = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'scout_evidence_bundles' "
            "AND column_name = 'scout_run_id'"
        )
    )
    row = r.fetchone()
    if row and row[0] != "uuid":
        return
    op.drop_constraint(
        "scout_evidence_bundles_scout_run_id_fkey",
        "scout_evidence_bundles",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_scout_evidence_bundles_scout_run_id",
        table_name="scout_evidence_bundles",
    )
    op.add_column(
        "scout_evidence_bundles",
        sa.Column("scout_run_id_int", sa.Integer(), nullable=True),
    )
    # Delete orphan bundles (run no longer exists) so UPDATE can backfill all rows
    # and we can safely set NOT NULL. Ensures clean, reversible downgrade.
    conn.execute(
        sa.text(
            "DELETE FROM scout_evidence_bundles sb WHERE NOT EXISTS "
            "(SELECT 1 FROM scout_runs sr WHERE sr.run_id = sb.scout_run_id)"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE scout_evidence_bundles sb SET scout_run_id_int = sr.id "
            "FROM scout_runs sr WHERE sr.run_id = sb.scout_run_id"
        )
    )
    op.drop_column("scout_evidence_bundles", "scout_run_id")
    op.alter_column(
        "scout_evidence_bundles",
        "scout_run_id_int",
        new_column_name="scout_run_id",
        nullable=False,
    )
    op.create_foreign_key(
        "scout_evidence_bundles_scout_run_id_fkey",
        "scout_evidence_bundles",
        "scout_runs",
        ["scout_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_scout_evidence_bundles_scout_run_id",
        "scout_evidence_bundles",
        ["scout_run_id"],
        unique=False,
    )
