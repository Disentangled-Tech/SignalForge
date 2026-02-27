"""Merge scout_tables and merge_checksum_heads into one head.

Revision ID: 20260227_merge_scout
Revises: 20260227_scout_tables, 20260233_merge_checksum_heads
Create Date: 2026-02-27

Single head so 'alembic upgrade head' succeeds.
"""

from collections.abc import Sequence

revision: str = "20260227_merge_scout"
down_revision: str | tuple[str, ...] | None = (
    "20260227_scout_tables",
    "20260233_merge_checksum_heads",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
