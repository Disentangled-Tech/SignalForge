"""Add unique constraint on signal_instances (entity_id, signal_id, pack_id) (Phase 2, Issue #192).

Revision ID: 20260224_signal_instances_unique
Revises: 20260224_job_runs_indexes
Create Date: 2026-02-24

Enables upsert by natural key for deriver engine idempotency.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260224_signal_instances_unique"
down_revision: str | None = "20260224_job_runs_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Pre-check: fail with clear message if duplicates exist (maintainer review)
    conn = op.get_bind()
    dup = conn.execute(
        sa.text(
            "SELECT entity_id, signal_id, pack_id FROM signal_instances "
            "GROUP BY entity_id, signal_id, pack_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if dup:
        raise RuntimeError(
            f"Duplicate signal_instances found: {len(dup)} rows. "
            "Resolve duplicates before migration (e.g. deduplicate by keeping "
            "min(first_seen), max(last_seen) per entity_id, signal_id, pack_id)."
        )
    op.create_unique_constraint(
        "uq_signal_instances_entity_signal_pack",
        "signal_instances",
        ["entity_id", "signal_id", "pack_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_signal_instances_entity_signal_pack",
        "signal_instances",
        type_="unique",
    )
