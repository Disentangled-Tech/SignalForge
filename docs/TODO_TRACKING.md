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

### M7 Verification Gate — config vs. doc (follow-up)

- **Location**: `app/config.py`, [docs/discovery_scout.md](discovery_scout.md)
- **TODO**: discovery_scout.md documents `SCOUT_VERIFICATION_GATE_ENABLED` and `scout_verification_gate_enabled`, but `app/config.py` does not define this setting. Either add `scout_verification_gate_enabled` to `app/config.py` and wire it where the gate is toggled, or add a short note in the doc (e.g. “(when implemented)” or “optional; add to config when enabling the gate”) so readers aren’t surprised it’s missing in code.
- **Reference**: Verification Gate (Issue #278), M7 documentation.

### M7 evidence-store.md markdown lint (follow-up)

- **Location**: [docs/evidence-store.md](evidence-store.md)
- **TODO**: Fix existing MD060 table-style warnings in evidence-store.md (sections 2, 3, 5, 6 tables) in a separate docs-only PR so the repo’s markdown lint is clean.

### M7 Pre-existing test failures (follow-up)

- **Locations**: `tests/test_daily_aggregation.py`, `tests/test_deriver_engine.py`
- **TODO**: Five failing tests (daily_aggregation ranked output shape expects `company_name`; deriver_engine pack_id / return type / events_skipped). Plan a separate fix so the full suite is green and invariants are preserved. Do not weaken assertions or remove tests.

## Reference

- Code review checklist: `.cursor/commands/review_code.md`
- ADR-001: Pack Architecture
