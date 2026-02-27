"""Add scout_runs and scout_evidence_bundles tables (Evidence-Only Scout).

Revision ID: 20260227_scout_tables
Revises: 20260227_fractional_cfo_v1
Create Date: 2026-02-27

Additive only: no changes to companies, signal_events, or signal_instances.
Per plan Step 4 / Milestone M3.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260227_scout_tables"
down_revision: str | None = "20260227_fractional_cfo_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_MARKER_TABLE = "_alembic_20260227_scout_tables_created"


def upgrade() -> None:
    conn = op.get_bind()
    # Idempotent for merge: 20260228_scout_runs (other branch) may have already created these.
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'scout_runs'"
        )
    )
    if result.scalar() is not None:
        return  # Tables already exist from 20260228_scout_runs branch

    op.create_table(
        "scout_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("page_fetch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scout_runs_run_id", "scout_runs", ["run_id"], unique=True)

    op.create_table(
        "scout_evidence_bundles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "scout_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("candidate_company_name", sa.String(length=255), nullable=False),
        sa.Column("company_website", sa.String(length=2048), nullable=False),
        sa.Column("why_now_hypothesis", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "missing_information",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("raw_llm_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["scout_run_id"],
            ["scout_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scout_evidence_bundles_scout_run_id",
        "scout_evidence_bundles",
        ["scout_run_id"],
        unique=False,
    )
    # Record that we created these tables so downgrade only drops when we created.
    op.create_table(
        _MARKER_TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
    )
    conn.execute(sa.text(f"INSERT INTO {_MARKER_TABLE} (id) VALUES (1)"))


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_schema = 'public' AND table_name = '{_MARKER_TABLE}'"
        )
    )
    if result.scalar() is None:
        return  # Tables were created by other branch (20260228_scout_runs)
    op.drop_index("ix_scout_evidence_bundles_scout_run_id", table_name="scout_evidence_bundles")
    op.drop_table("scout_evidence_bundles")
    op.drop_index("ix_scout_runs_run_id", table_name="scout_runs")
    op.drop_table("scout_runs")
    op.drop_table(_MARKER_TABLE)
