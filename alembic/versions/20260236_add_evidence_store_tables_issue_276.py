"""Add evidence store tables (M2, Issue #276).

Revision ID: 20260236_evidence_store
Revises: 20260235_merge_all
Create Date: 2026-02-27

Immutable evidence store: evidence_bundles, evidence_sources, evidence_bundle_sources,
evidence_claims, evidence_quarantine. Additive only; no changes to existing tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260236_evidence_store"
down_revision: str | None = "20260235_merge_all"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # evidence_sources: standalone, deduplicated by (content_hash, url)
    op.create_table(
        "evidence_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_sources_content_hash_url",
        "evidence_sources",
        ["content_hash", "url"],
        unique=True,
    )

    # evidence_bundles: append-only, versioned
    op.create_table(
        "evidence_bundles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scout_version", sa.String(length=128), nullable=False),
        sa.Column("core_taxonomy_version", sa.String(length=64), nullable=False),
        sa.Column("core_derivers_version", sa.String(length=64), nullable=False),
        sa.Column(
            "pack_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("run_context", postgresql.JSONB(), nullable=True),
        sa.Column("raw_model_output", postgresql.JSONB(), nullable=True),
        sa.Column("structured_payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["pack_id"],
            ["signal_packs.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_evidence_bundles_core_versions",
        "evidence_bundles",
        ["core_taxonomy_version", "core_derivers_version"],
        unique=False,
    )

    # evidence_bundle_sources: join table
    op.create_table(
        "evidence_bundle_sources",
        sa.Column("bundle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("bundle_id", "source_id"),
        sa.ForeignKeyConstraint(
            ["bundle_id"],
            ["evidence_bundles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["evidence_sources.id"],
            ondelete="CASCADE",
        ),
    )

    # evidence_claims: scoped to bundle, source_ids JSONB
    op.create_table(
        "evidence_claims",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bundle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("source_ids", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["bundle_id"],
            ["evidence_bundles.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_evidence_claims_bundle_id",
        "evidence_claims",
        ["bundle_id"],
        unique=False,
    )

    # evidence_quarantine: no FK to bundles
    op.create_table(
        "evidence_quarantine",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("evidence_quarantine")
    op.drop_index("ix_evidence_claims_bundle_id", table_name="evidence_claims")
    op.drop_table("evidence_claims")
    op.drop_table("evidence_bundle_sources")
    op.drop_index("ix_evidence_bundles_core_versions", table_name="evidence_bundles")
    op.drop_table("evidence_bundles")
    op.drop_index(
        "ix_evidence_sources_content_hash_url",
        table_name="evidence_sources",
    )
    op.drop_table("evidence_sources")
