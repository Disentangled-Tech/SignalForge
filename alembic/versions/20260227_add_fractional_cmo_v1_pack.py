"""Add fractional_cmo_v1 pack to signal_packs (Issue #288 M2).

Revision ID: 20260227_fractional_cmo_v1
Revises: 20260227_fractional_cto_v2_checksum
Create Date: 2026-02-27

Inserts fractional_cmo_v1 pack (v2 layout: analysis_weights, esl_rubric, prompt_bundles).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260227_fractional_cmo_v1"
down_revision: str | None = "20260227_fractional_cto_v2_checksum"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FRACTIONAL_CMO_PACK_UUID = "d3e4f5a6-b7c8-9d01-ef23-4567890abcde"


def upgrade() -> None:
    from app.packs.loader import load_pack

    pack = load_pack("fractional_cmo_v1", "1")
    checksum = pack.config_checksum
    op.execute(
        sa.text(
            "INSERT INTO signal_packs (id, pack_id, version, industry, description, is_active, created_at, updated_at, config_checksum) "
            "VALUES (CAST(:id AS uuid), 'fractional_cmo_v1', '1', 'fractional_cmo', "
            "'Fractional CMO signal pack (Issue #288 M2)', true, now(), now(), :cs)"
        ).bindparams(id=FRACTIONAL_CMO_PACK_UUID, cs=checksum)
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM signal_packs WHERE pack_id = 'fractional_cmo_v1' AND version = '1'")
    )
