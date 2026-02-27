"""Merge scout_runs head with fractional_cfo_v1 head (single head for CI).

Revision ID: 20260228_merge_heads
Revises: 20260228_scout_runs, 20260227_fractional_cfo_v1
Create Date: 2026-02-28

No schema changes. Unifies migration graph so 'alembic upgrade head' succeeds.
"""
from collections.abc import Sequence

revision: str = "20260228_merge_heads"
down_revision: str | tuple[str, ...] | None = (
    "20260228_scout_runs",
    "20260227_fractional_cfo_v1",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
