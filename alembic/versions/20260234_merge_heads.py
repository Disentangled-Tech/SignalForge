"""Merge fractional_cfo and merge_checksum_heads (Issue #289 follow-up).

Revision ID: 20260234_merge_heads
Revises: 20260227_fractional_cfo_v1, 20260233_merge_checksum_heads
Create Date: 2026-02-27

Two heads existed: 20260227_fractional_cfo_v1 (CFO pack) and 20260233_merge_checksum_heads
(previous checksum merge). This merge has no schema changes; it unifies the graph so
'alembic upgrade head' succeeds.
"""

from collections.abc import Sequence

revision: str = "20260234_merge_heads"
down_revision: str | tuple[str, ...] | None = (
    "20260227_fractional_cfo_v1",
    "20260233_merge_checksum_heads",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
