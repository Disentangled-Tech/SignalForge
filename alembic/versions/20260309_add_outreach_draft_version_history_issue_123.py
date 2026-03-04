"""Add draft_generation_number and draft_version_history to outreach_recommendations (Issue #123 M1).

Revision ID: 20260309_ore_draft_version
Revises: 20260308_config_checksum_forbidden
Create Date: 2026-03-09

Additive only: draft_generation_number (integer, default 0) for per-recommendation
regeneration counter; draft_version_history (JSONB, nullable) for version history.
No constraint or unique change. generation_version remains pack/config version.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260309_ore_draft_version"
down_revision: str | None = "20260308_config_checksum_forbidden"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outreach_recommendations",
        sa.Column(
            "draft_generation_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "outreach_recommendations",
        sa.Column("draft_version_history", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outreach_recommendations", "draft_version_history")
    op.drop_column("outreach_recommendations", "draft_generation_number")
