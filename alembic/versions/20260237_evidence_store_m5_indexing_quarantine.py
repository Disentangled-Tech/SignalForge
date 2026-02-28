"""M5: Evidence store indexing and immutability trigger (Issue #276).

Adds: index on evidence_sources.content_hash for lookups; expression index on
evidence_bundles (run_context domain/name) for domain+name dedupe lookups;
optional trigger to reject UPDATE/DELETE on evidence_bundles (immutability).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260237_evidence_m5"
down_revision: str | None = "20260236_evidence_store"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Trigger function and trigger name for downgrade
_TRIGGER_NAME = "tr_evidence_bundles_immutable"
_FUNCTION_NAME = "reject_evidence_bundles_update_delete"


def upgrade() -> None:
    # Index on content_hash for lookups by hash (without url)
    op.create_index(
        "ix_evidence_sources_content_hash",
        "evidence_sources",
        ["content_hash"],
        unique=False,
    )
    # Expression index for domain+name dedupe lookups (run_context JSONB)
    op.execute(
        "CREATE INDEX ix_evidence_bundles_run_context_domain_name ON evidence_bundles "
        "((run_context->>'domain'), (run_context->>'name'))"
    )
    # Optional: reject UPDATE/DELETE on evidence_bundles (immutability)
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION_NAME}()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'evidence_bundles is immutable: updates not allowed';
            ELSIF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'evidence_bundles is immutable: deletes not allowed';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_NAME}
        BEFORE UPDATE OR DELETE ON evidence_bundles
        FOR EACH ROW EXECUTE PROCEDURE {_FUNCTION_NAME}();
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON evidence_bundles;")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION_NAME}();")
    op.execute("DROP INDEX IF EXISTS ix_evidence_bundles_run_context_domain_name;")
    op.drop_index("ix_evidence_sources_content_hash", table_name="evidence_sources")
