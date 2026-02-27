"""Merge config_checksum heads (Issue #288).

Revision ID: 20260233_merge_checksum_heads
Revises: 20260227_fractional_cto_v2_checksum, 20260232_config_checksum_v2
Create Date: 2026-02-27

Two migrations (20260227 and 20260232) both revised 20260231_lead_feed_band
(via 20260226 for 20260227), producing multiple heads. This merge revision
has no schema changes; it unifies the migration graph so 'alembic upgrade head'
succeeds.
"""

from collections.abc import Sequence

revision: str = "20260233_merge_checksum_heads"
down_revision: str | tuple[str, ...] | None = (
    "20260227_fractional_cto_v2_checksum",
    "20260232_config_checksum_v2",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
