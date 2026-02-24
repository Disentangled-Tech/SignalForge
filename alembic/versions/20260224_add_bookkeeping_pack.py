"""Add bookkeeping_v1 pack to signal_packs (Issue #175, Phase 3).

Revision ID: 20260224_bookkeeping_pack
Revises: 20260224_esl_decision_cols
Create Date: 2026-02-24

Inserts bookkeeping_v1 pack for ESL gate testing (blocked_signals: financial_distress).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260224_bookkeeping_pack"
down_revision: str | None = "20260224_esl_decision_cols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BOOKKEEPING_PACK_UUID = "b2c3d4e5-f6a7-8b90-cdef-123456789012"


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO signal_packs (id, pack_id, version, industry, description, is_active, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), 'bookkeeping_v1', '1', 'bookkeeping', "
            "'Bookkeeping pack with blocked_signals (financial_distress)', true, now(), now())"
        ).bindparams(id=BOOKKEEPING_PACK_UUID)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM signal_packs WHERE pack_id = 'bookkeeping_v1' AND version = '1'"
        )
    )
