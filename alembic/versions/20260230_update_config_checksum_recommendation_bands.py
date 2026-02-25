"""Update config_checksum for fractional_cto_v1 after recommendation_bands (Issue #242).

Revision ID: 20260230_config_checksum_bands
Revises: 20260229_user_ws_user_idx
Create Date: 2026-02-30

When scoring.yaml gains recommendation_bands, config_checksum changes.
This migration updates signal_packs.config_checksum to match the current pack config.

Downgrade: No-op. The checksum is not reverted. To fully downgrade, revert
scoring.yaml (remove recommendation_bands) and redeploy before downgrading.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260230_config_checksum_bands"
down_revision: str | None = "20260229_user_ws_user_idx"
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
            "run earlier migrations (e.g. 20260223_signal_packs) first"
        )


def downgrade() -> None:
    # No-op: cannot revert to previous checksum without reverting scoring.yaml
    pass
