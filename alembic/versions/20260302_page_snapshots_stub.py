"""Stub for page_snapshots revision (M2 not yet in repo; M3 diff detection only).

Revision ID: 20260302_page_snapshots
Revises: 20260302_evidence_bundle_id
Create Date: 2026-03-02

Allows migration chain to resolve when test DB or other branch has this head.
M2 (Page snapshot storage) will replace this with the real page_snapshots table
migration (same revision id or new id and this file removed).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260302_page_snapshots"
down_revision: str | None = "20260302_evidence_bundle_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op until M2 adds page_snapshots table."""
    pass


def downgrade() -> None:
    """No-op."""
    pass
