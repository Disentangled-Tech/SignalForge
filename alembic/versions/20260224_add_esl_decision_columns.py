"""Add esl_decision, esl_reason_code, sensitivity_level to engagement_snapshots (Phase 4, Issue #175).

Revision ID: 20260224_esl_decision_cols
Revises: 20260224_evidence_event_ids
Create Date: 2026-02-24

Add dedicated columns for ESL decision gate output. Backfill existing rows
with esl_decision='allow', esl_reason_code='legacy' where NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260224_esl_decision_cols"
down_revision: str | None = "20260224_evidence_event_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "engagement_snapshots",
        sa.Column("esl_decision", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "engagement_snapshots",
        sa.Column("esl_reason_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "engagement_snapshots",
        sa.Column("sensitivity_level", sa.String(length=32), nullable=True),
    )
    # Backfill: existing rows get allow/legacy
    op.execute(
        sa.text(
            "UPDATE engagement_snapshots SET esl_decision = 'allow', esl_reason_code = 'legacy' "
            "WHERE esl_decision IS NULL"
        )
    )

    # JobRun audit: count of companies with esl_decision=suppress (Phase 4, Issue #175)
    op.add_column(
        "job_runs",
        sa.Column("companies_esl_suppressed", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_runs", "companies_esl_suppressed")
    op.drop_column("engagement_snapshots", "sensitivity_level")
    op.drop_column("engagement_snapshots", "esl_reason_code")
    op.drop_column("engagement_snapshots", "esl_decision")
