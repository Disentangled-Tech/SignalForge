"""add unique constraint on briefing_items (company_id, briefing_date)

Revision ID: f1a2b3c4d5e6
Revises: e77e9209fe33
Create Date: 2026-02-17

Prevents duplicate companies on the Daily Briefing. Cleans up existing
duplicates (keeps most recent by created_at) before adding the constraint.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e77e9209fe33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Remove duplicate BriefingItems: keep one per (company_id, briefing_date)
    #    with the most recent created_at; use id as tiebreaker when created_at is equal.
    op.execute("""
        DELETE FROM briefing_items a
        WHERE EXISTS (
            SELECT 1 FROM briefing_items b
            WHERE a.company_id = b.company_id
              AND a.briefing_date IS NOT DISTINCT FROM b.briefing_date
              AND (
                a.created_at < b.created_at
                OR (a.created_at = b.created_at AND a.id < b.id)
              )
        )
    """)

    # 2. Add unique index (partial: only when briefing_date is not null)
    op.execute(
        "CREATE UNIQUE INDEX uq_briefing_items_company_date "
        "ON briefing_items (company_id, briefing_date) "
        "WHERE briefing_date IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_briefing_items_company_date")
