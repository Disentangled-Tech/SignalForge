"""Issue #240 schema validation: document alignment, no destructive changes.

Revision ID: 20260226_issue_240
Revises: 20260225_analysis_pack_id
Create Date: 2026-02-26

Schema mapping (Issue #240 acceptance criteria):
- companies          ↔ companies (existing; id, domain, website_url, cto_need_score, etc.)
- company_signal_events ↔ signal_events (existing; company_id, event_time, pack_id, source, source_event_id)
- company_scores     ↔ readiness_snapshots (existing; company_id, as_of, composite, pack_id, etc.)

Indexes (Issue #240 vs current):
- companies.domain: ix_companies_domain (unique, partial WHERE domain IS NOT NULL) — present (20260218_aliases)
- company_signal_events.event_date: event_time (datetime) — ix_signal_events_company_event_time,
  ix_signal_events_event_type_event_time cover (company_id, event_time), (event_type, event_time).
  No DATE(event_time) index added; defer if date-range queries dominate.
- company_scores.score: ix_readiness_snapshots_as_of_composite (as_of, composite DESC) — present

Unique constraint (duplicate events):
- uq_signal_events_source_source_event_id on (source, source_event_id) WHERE source_event_id IS NOT NULL — present (b2c3d4e5f6a7)

JSON/JSONB: signal_events.raw, readiness_snapshots.explain — compliant.

No schema changes in this migration; validation only.
"""

from collections.abc import Sequence

revision: str = "20260226_issue_240"
down_revision: str | None = "20260225_analysis_pack_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema changes; Issue #240 acceptance criteria met by existing schema."""
    pass


def downgrade() -> None:
    """No schema changes to revert."""
    pass
