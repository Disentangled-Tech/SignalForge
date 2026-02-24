# TODO Tracking (Code Review Follow-Ups)

Tracks outstanding TODOs and follow-ups from maintainer reviews.

## Completed

- **OutreachHistory workspace_id** (Issue #225 follow-up): Added `workspace_id` column to `outreach_history`; `_batch_outreach_summary_for_entities` filters by workspace; `create_outreach_record` accepts optional `workspace_id`; `refresh_outreach_summary_for_entity` scopes by workspace when provided.
- **minimum_threshold in lead_feed**: `build_lead_feed_from_snapshots` and `upsert_lead_feed_from_snapshots` now exclude entities where `rs.composite < minimum_threshold` when pack defines it.

## Pending

### Briefing multi-tenant scoping

- **Location**: `app/api/briefing_views.py` — `get_briefing_data()`
- **TODO**: Scope by `workspace_id` when multi-workspace is enabled; `get_emerging_companies` and pack resolution should use workspace active pack.
- **Reference**: [docs/MULTI_TENANT_BRIEFING_TODO.md](MULTI_TENANT_BRIEFING_TODO.md)

### create_outreach_record workspace context

- **Location**: `app/services/outreach_history.py` — `create_outreach_record()`
- **TODO**: When multi-tenant is enabled, callers (views/API) must pass `workspace_id` from request/session context. Currently defaults to `DEFAULT_WORKSPACE_ID`.

### minimum_threshold in other surfaces

- **Locations**: `get_emerging_companies()`, `get_weekly_review_companies()`
- **Reference**: [docs/MINIMUM_THRESHOLD_ENFORCEMENT.md](MINIMUM_THRESHOLD_ENFORCEMENT.md)

## Reference

- Code review checklist: `.cursor/commands/review_code.md`
- ADR-001: Pack Architecture
