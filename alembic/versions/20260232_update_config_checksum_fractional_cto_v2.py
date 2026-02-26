"""Update config_checksum for fractional_cto_v1 after Pack v2 (M6).

Revision ID: 20260232_config_checksum_v2
Revises: 20260231_lead_feed_band
Create Date: 2026-02-26

When fractional_cto_v1 is migrated to schema_version "2" (Pack v2 contract M6),
config_checksum changes. This migration updates signal_packs.config_checksum
to match the current pack config.

Downgrade: No-op. The checksum is not reverted.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260232_config_checksum_v2"
down_revision: str | None = "20260231_lead_feed_band"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.packs.loader import load_pack

    pack = load_pack("fractional_cto_v1", "1")
    checksum = pack.config_checksum
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "UPDATE signal_packs SET config_checksum = :cs "
            "WHERE pack_id = 'fractional_cto_v1' AND version = '1'"
        ).bindparams(cs=checksum)
    )
    if result.rowcount == 0:
        raise RuntimeError(
            "signal_packs row for fractional_cto_v1 v1 not found; "
            "run earlier migrations first"
        )


def downgrade() -> None:
    # No-op: cannot revert to previous checksum without reverting pack.json
    pass
