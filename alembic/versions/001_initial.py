"""Initial schema placeholder.

Revision ID: 001
Revises: 
Create Date: 2025-02-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Initial upgrade - no tables yet. Add models and run autogenerate for real migrations."""
    pass


def downgrade() -> None:
    """Initial downgrade."""
    pass
