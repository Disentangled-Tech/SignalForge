"""Add core pack sentinel to signal_packs (Issue #287, M1).

Revision ID: 20260226_core_pack_sentinel
Revises: 20260231_lead_feed_band
Create Date: 2026-02-26

Inserts a single row with pack_id='core', version='1' so that SignalInstance
can reference it via FK. Derive/score use this as the canonical pack_id for
core signal instances (no behavior change in this migration).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260226_core_pack_sentinel"
down_revision: str | None = "20260231_lead_feed_band"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valid UUID (hex 0-9a-f only); mnemonic "core" pack sentinel
CORE_PACK_UUID = "c0de0000-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO signal_packs (id, pack_id, version, industry, description, is_active, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), 'core', '1', NULL, 'Core pack sentinel for SignalInstance FK (Issue #287)', true, now(), now())"
        ).bindparams(id=CORE_PACK_UUID)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM signal_packs WHERE pack_id = 'core' AND version = '1'"
        )
    )
