"""Merge all heads after branch merge (scout + main).

Revision ID: 20260235_merge_all
Revises: 20260227_merge_scout, 20260228_scout_workspace, 20260234_merge_heads, 20260234_merge_scout_checksum
Create Date: 2026-02-27

No schema changes. Unifies migration graph after merging feature/scout-m3-m5-evidence-only with main.
"""

from collections.abc import Sequence

revision: str = "20260235_merge_all"
down_revision: str | tuple[str, ...] | None = (
    "20260227_merge_scout",
    "20260228_scout_workspace",
    "20260234_merge_heads",
    "20260234_merge_scout_checksum",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
