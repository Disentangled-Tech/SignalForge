"""Add scout_runs and scout_evidence_bundles tables (M3, Issue #275).

Revision ID: 20260228_scout_runs
Revises: 20260233_merge_checksum_heads
Create Date: 2026-02-28

Discovery Scout Evidence-Only mode: additive only. No FK to companies or
signal_events. scout_evidence_bundles references scout_runs only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260228_scout_runs"
down_revision: str | None = "20260233_merge_checksum_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scout_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "page_fetch_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scout_runs_run_id",
        "scout_runs",
        ["run_id"],
        unique=True,
    )

    op.create_table(
        "scout_evidence_bundles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "scout_run_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "candidate_company_name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "company_website",
            sa.String(length=2048),
            nullable=False,
        ),
        sa.Column(
            "why_now_hypothesis",
            sa.String(length=2000),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "missing_information",
            postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("raw_llm_output", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["scout_run_id"],
            ["scout_runs.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_scout_evidence_bundles_scout_run_id",
        "scout_evidence_bundles",
        ["scout_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scout_evidence_bundles_scout_run_id",
        table_name="scout_evidence_bundles",
    )
    op.drop_table("scout_evidence_bundles")
    op.drop_index("ix_scout_runs_run_id", table_name="scout_runs")
    op.drop_table("scout_runs")
