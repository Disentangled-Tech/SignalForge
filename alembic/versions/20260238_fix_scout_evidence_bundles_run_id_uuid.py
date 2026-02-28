"""Fix scout_evidence_bundles.scout_run_id to UUID (align ORM with DB).

Revision ID: 20260238_scout_run_id_uuid
Revises: 20260237_evidence_m5
Create Date: 2026-02-28

Branch 20260228 created scout_evidence_bundles with scout_run_id INTEGER FK to
scout_runs.id; the ORM (ScoutEvidenceBundle) expects UUID FK to scout_runs.run_id.
This migration aligns the schema with the ORM so run_scout and tests pass.
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
    # Remove orphans so nullable=False is safe: bundles whose scout_run was deleted.
    op.execute(
        sa.text(
            "DELETE FROM scout_evidence_bundles WHERE scout_run_id NOT IN "
            "(SELECT run_id FROM scout_runs)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE scout_evidence_bundles SET scout_run_id_int = "
            "(SELECT id FROM scout_runs WHERE scout_runs.run_id = scout_evidence_bundles.scout_run_id)"
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
