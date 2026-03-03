"""add raw_html to signal_records

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-02-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signal_records",
        sa.Column("raw_html", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE signal_records DROP COLUMN IF EXISTS raw_html"))
