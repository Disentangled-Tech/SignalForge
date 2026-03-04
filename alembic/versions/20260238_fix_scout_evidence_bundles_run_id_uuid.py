"""Fix scout_evidence_bundles.scout_run_id to UUID (align ORM with DB).

Revision ID: 20260238_scout_run_id_uuid
Revises: 20260237_evidence_m5
Create Date: 2026-02-28

Branch 20260228 created scout_evidence_bundles with scout_run_id INTEGER FK to
scout_runs.id; the ORM (ScoutEvidenceBundle) expects UUID FK to scout_runs.run_id.
This migration aligns the schema with the ORM so run_scout and tests pass.
Downgrade: deletes orphan bundles (run no longer exists) before backfill for clean reversible downgrade.
Downgrade looks up the FK constraint by name from pg_constraint so it runs whether the FK was
created with the standard name or an auto-generated name (e.g. from 20260227 branch).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260238_scout_run_id_uuid"
down_revision: str | None = "20260237_evidence_m5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Only run if scout_evidence_bundles has integer scout_run_id (from 20260228 branch).
    conn = op.get_bind()
    r = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'scout_evidence_bundles' "
            "AND column_name = 'scout_run_id'"
        )
    )
    row = r.fetchone()
    if row is None:
        return  # Table or column missing (e.g. 20260227 branch only)
    if row[0] not in ("integer", "smallint"):
        return  # Already UUID (e.g. 20260227 branch created the table)

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
        sa.Column("scout_run_uuid", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE scout_evidence_bundles SET scout_run_uuid = "
            "(SELECT run_id FROM scout_runs WHERE scout_runs.id = scout_evidence_bundles.scout_run_id)"
        )
    )
    op.drop_column("scout_evidence_bundles", "scout_run_id")
    op.alter_column(
        "scout_evidence_bundles",
        "scout_run_uuid",
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
    if row is None or row[0] != "uuid":
        return

    # Drop FK by actual name: 20260227 branch may have created it with auto-generated name.
    # IF EXISTS allows test_migration_20260238_* (which drops constraint to create orphan) to pass.
    r2 = conn.execute(
        sa.text(
            "SELECT conname FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "WHERE t.relname = 'scout_evidence_bundles' AND c.contype = 'f' "
            "AND EXISTS (SELECT 1 FROM pg_attribute a "
            "JOIN pg_class t2 ON a.attrelid = t2.oid WHERE t2.relname = 'scout_evidence_bundles' "
            "AND a.attname = 'scout_run_id' AND a.attnum = ANY(c.conkey) AND NOT a.attisdropped)"
        )
    )
    fk_row = r2.fetchone()
    if fk_row:
        # conname comes from pg_constraint (system catalog); not user input. We escape
        # double-quotes in the identifier for safe SQL quoting when dropping by name.
        conname = str(fk_row[0])
        conn.execute(
            sa.text(
                f'ALTER TABLE scout_evidence_bundles DROP CONSTRAINT IF EXISTS "{conname.replace(chr(34), chr(34) + chr(34))}"'
            )
        )
    else:
        conn.execute(
            sa.text(
                "ALTER TABLE scout_evidence_bundles "
                "DROP CONSTRAINT IF EXISTS scout_evidence_bundles_scout_run_id_fkey"
            )
        )
    op.drop_index(
        "ix_scout_evidence_bundles_scout_run_id",
        table_name="scout_evidence_bundles",
        if_exists=True,
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
