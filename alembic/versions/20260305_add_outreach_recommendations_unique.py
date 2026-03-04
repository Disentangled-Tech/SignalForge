"""Add UNIQUE(company_id, as_of, pack_id) to outreach_recommendations (Issue #115 M3).

Revision ID: 20260305_ore_unique
Revises: 20260305_merge_heads
Create Date: 2026-03-05

Deduplicates existing rows (keep one per key with max id), drops the non-unique
index on (company_id, as_of), adds unique constraint uq_outreach_recommendations_company_as_of_pack.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260305_ore_unique"
down_revision: str | None = "20260305_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Deduplicate: keep one row per (company_id, as_of, pack_id), the one with max(id)
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            WITH dupes AS (
                SELECT id FROM (
                    SELECT id,
                        ROW_NUMBER() OVER (
                            PARTITION BY company_id, as_of, pack_id
                            ORDER BY id DESC
                        ) AS rn
                    FROM outreach_recommendations
                ) sub
                WHERE sub.rn > 1
            )
            DELETE FROM outreach_recommendations
            WHERE id IN (SELECT id FROM dupes)
            """
        )
    )

    # 2. Drop existing non-unique index
    op.drop_index(
        "ix_outreach_recommendations_company_as_of",
        table_name="outreach_recommendations",
        if_exists=True,
    )

    # 3. Create unique constraint (company_id, as_of, pack_id)
    op.create_unique_constraint(
        "uq_outreach_recommendations_company_as_of_pack",
        "outreach_recommendations",
        ["company_id", "as_of", "pack_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_outreach_recommendations_company_as_of_pack",
        "outreach_recommendations",
        type_="unique",
    )
    op.create_index(
        "ix_outreach_recommendations_company_as_of",
        "outreach_recommendations",
        ["company_id", "as_of"],
        unique=False,
    )
