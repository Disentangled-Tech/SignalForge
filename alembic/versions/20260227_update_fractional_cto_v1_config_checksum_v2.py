"""Update config_checksum for fractional_cto_v1 after Pack v2 migration (Issue #288 M1).

Revision ID: 20260227_fractional_cto_v2_checksum
Revises: 20260226_core_pack_sentinel
Create Date: 2026-02-27

fractional_cto_v1 is migrated to Pack v2 (schema_version "2"): analysis_weights.yaml,
esl_rubric.yaml, prompt_bundles; taxonomy and derivers removed. This migration
updates signal_packs.config_checksum to match the current pack config.

Downgrade: No-op. The checksum is not reverted.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260227_fractional_cto_v2_checksum"
down_revision: str | None = "20260226_core_pack_sentinel"
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
    # No-op: cannot revert to previous checksum without reverting pack dir to v1
    pass
