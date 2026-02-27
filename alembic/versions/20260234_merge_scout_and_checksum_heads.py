"""Merge scout_tables and merge_checksum_heads into single head.

Revision ID: 20260234_merge_scout_checksum
Revises: 20260227_scout_tables, 20260233_merge_checksum_heads
Create Date: 2026-02-27

No schema changes; unifies migration graph after adding scout tables.
"""

from collections.abc import Sequence

revision: str = "20260234_merge_scout_checksum"
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
