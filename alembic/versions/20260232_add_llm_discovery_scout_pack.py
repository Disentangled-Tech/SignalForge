"""Add llm_discovery_scout_v0 pack to signal_packs (Phase 3, Evidence-Only mode).

Revision ID: 20260232_discovery_scout
Revises: 20260231_lead_feed_band
Create Date: 2026-02-32

Inserts llm_discovery_scout_v0 pack for evidence-only discovery scans.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260232_discovery_scout"
down_revision: str | None = "20260231_lead_feed_band"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LLM_DISCOVERY_SCOUT_PACK_UUID = "c3d4e5f6-a7b8-90cd-ef12-345678901234"


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO signal_packs (id, pack_id, version, industry, description, is_active, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), 'llm_discovery_scout_v0', '1', 'discovery', "
            "'LLM Discovery Scout — evidence-only mode, no outreach drafts', true, now(), now())"
        ).bindparams(id=LLM_DISCOVERY_SCOUT_PACK_UUID)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM signal_packs WHERE pack_id = 'llm_discovery_scout_v0' AND version = '1'"
        )
    )
