"""add raw_html to signal_records

Revision ID: f1a2b3c4d5e6
Revises: e77e9209fe33
Create Date: 2026-02-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e77e9209fe33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "signal_records",
        sa.Column("raw_html", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("signal_records", "raw_html")
