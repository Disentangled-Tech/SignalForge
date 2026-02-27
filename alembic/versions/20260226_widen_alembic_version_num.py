"""Widen alembic_version.version_num so long revision IDs fit (test DB / CI).

Revision ID: widen_alembic_ver
Revises: 20260226_core_pack_sentinel
Create Date: 2026-02-26

Alembic creates alembic_version with version_num VARCHAR(32). Some revision IDs
(e.g. 20260227_fractional_cto_v2_checksum) are 35 chars. This migration widens
the column to VARCHAR(64) so upgrade head succeeds in fresh test DBs.

Downgrade: Only reverts to VARCHAR(32) if current version_num length <= 32,
so we never truncate or fail when a long revision ID was applied.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "widen_alembic_ver"
down_revision: str | None = "20260226_core_pack_sentinel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"))


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT version_num FROM alembic_version LIMIT 1"))
    row = result.fetchone()
    current = (row[0] or "") if row else ""
    if len(current) <= 32:
        op.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)"))
