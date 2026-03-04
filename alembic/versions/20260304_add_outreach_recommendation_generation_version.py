"""Add generation_version to outreach_recommendations (Issue #115 M1).

Revision ID: 20260304_ore_gen_version
Revises: 20260302_page_snapshots
Create Date: 2026-03-04

Adds nullable generation_version column for ORE output schema alignment.
No unique constraint or upsert in this revision; M2/M3 handle those.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260304_ore_gen_version"
down_revision: str | None = "20260302_page_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outreach_recommendations",
        sa.Column("generation_version", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outreach_recommendations", "generation_version")
