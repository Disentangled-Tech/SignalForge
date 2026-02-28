"""Initial schema placeholder.

Revision ID: 001
Revises:
Create Date: 2025-02-12

"""

from collections.abc import Sequence

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Initial upgrade - no tables yet. Add models and run autogenerate for real migrations."""
    pass


def downgrade() -> None:
    """Initial downgrade."""
    pass
