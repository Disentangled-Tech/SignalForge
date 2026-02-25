"""Update config_checksum for fractional_cto_v1 after recommendation_bands (Issue #242).

Revision ID: 20260230_config_checksum_bands
Revises: 20260229_user_ws_user_idx
Create Date: 2026-02-30

When scoring.yaml gains recommendation_bands, config_checksum changes.
This migration updates signal_packs.config_checksum to match the current pack config.
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
    op.execute(
        sa.text(
            "UPDATE signal_packs SET config_checksum = :cs "
            "WHERE pack_id = 'fractional_cto_v1' AND version = '1'"
        ).bindparams(cs=checksum)
    )


def downgrade() -> None:
    # No-op: cannot revert to previous checksum without reverting scoring.yaml
    pass
