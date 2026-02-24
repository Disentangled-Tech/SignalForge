"""Lead feed projection service (Phase 1, Issue #225, ADR-004)."""

from app.services.lead_feed.projection_builder import (
    build_lead_feed_from_snapshots,
    refresh_outreach_summary_for_entity,
    upsert_lead_feed_from_snapshots,
    upsert_lead_feed_row,
)
from app.services.lead_feed.query_service import (
    get_emerging_companies_from_feed,
    get_leads_from_feed,
    get_weekly_review_companies_from_feed,
)

__all__ = [
    "build_lead_feed_from_snapshots",
    "get_emerging_companies_from_feed",
    "get_leads_from_feed",
    "get_weekly_review_companies_from_feed",
    "refresh_outreach_summary_for_entity",
    "upsert_lead_feed_from_snapshots",
    "upsert_lead_feed_row",
]
