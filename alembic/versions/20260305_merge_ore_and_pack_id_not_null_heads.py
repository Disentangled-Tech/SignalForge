"""Merge ORE gen_version and pack_id NOT NULL heads (Issue #193 M1).

Revision ID: 20260305_merge_heads
Revises: 20260304_ore_gen_version, 20260304_pack_id_not_null
Create Date: 2026-03-05

Two heads existed: 20260304_ore_gen_version and 20260304_pack_id_not_null (Issue #193 M1).
This merge has no schema changes; it unifies the graph so 'alembic upgrade head' succeeds.
"""

from collections.abc import Sequence

revision: str = "20260305_merge_heads"
down_revision: str | tuple[str, ...] | None = (
    "20260304_ore_gen_version",
    "20260304_pack_id_not_null",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
