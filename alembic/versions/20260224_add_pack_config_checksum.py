"""Add config_checksum to signal_packs (Issue #190, Phase 3).

Revision ID: 20260224_config_checksum
Revises: ee6582573566
Create Date: 2026-02-24

- Add config_checksum column (nullable, 64 chars for SHA-256 hex)
- Backfill fractional_cto_v1 with computed checksum

REQUIREMENT (Option B - strict correctness):
  The packs/ directory and fractional_cto_v1 pack MUST be present and valid
  during migration. This migration calls load_pack("fractional_cto_v1", "1")
  to compute the checksum. If load_pack fails (FileNotFoundError, ValueError,
  ValidationError), the migration will fail and the upgrade will roll back.
  Deployment artifacts (Docker, CI, etc.) MUST include packs/fractional_cto_v1/.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260224_config_checksum"
down_revision: str | None = "ee6582573566"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signal_packs",
        sa.Column("config_checksum", sa.String(length=64), nullable=True),
    )

    # Backfill fractional_cto_v1 with computed checksum
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
    op.drop_column("signal_packs", "config_checksum")
