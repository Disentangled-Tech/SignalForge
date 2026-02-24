# Phases 2–4 + Lead Feed + Deriver Fixes

Closes #174, #175, #173, #225

## Summary

Implements Phases 2–4 of the scoring engine pack refactor, Lead Feed projection (Phase 1, Issue #225), deriver bug fixes, and maintainer-requested follow-ups.

### Phases 2–4 (Pack refactor)

- **Phase 2**: `minimum_threshold`, `disqualifier_signals`, parity harness; `evidence_event_ids` on signal_instances; pattern derivers
- **Phase 3**: Pack activation runtime; `workspace_id`/`pack_id` on run_score, run_derive, run_ingest; bookkeeping_v1 pack
- **Phase 4**: ESL decision gate (`esl_decision`, `esl_reason_code`, `sensitivity_level`); briefing filters suppressed companies; `companies_esl_suppressed` audit

### Lead Feed (Issue #225, ADR-004)

- **`POST /internal/run_update_lead_feed`**: Project `lead_feed` from ReadinessSnapshot + EngagementSnapshot; workspace/pack-scoped; idempotent
- **`lead_feed` table**: Unique per `(workspace_id, pack_id, entity_id)`; excludes suppressed entities

### Deriver bug fixes

- **source_fields**: Use `ALLOWED_PATTERN_SOURCE_FIELDS` (title, summary, url, source) instead of `_DEFAULT_PATTERN_SOURCE_FIELDS` (title, summary only). Packs specifying `["url"]` or `["source"]` now work at runtime.
- **evidence_event_ids merge**: Merge + deduplicate on upsert (PostgreSQL `jsonb_agg(DISTINCT elem)`). Prevents unbounded growth on re-runs; fixes session-cache test flakiness with `db.expire_all()`.

### Follow-ups

- **`test_build_isolates_by_workspace_and_pack`**: Verifies run_update_lead_feed writes only to specified workspace+pack (no cross-tenant leakage)
- **`docs/MULTI_TENANT_BRIEFING_TODO.md`**: Tracks briefing workspace scoping for when multi-workspace is enabled
- **`docs/pipeline.md`**: Documents `run_update_lead_feed` query params and validation

## Changes

### Phase 2 – Pack config & scoring

- **`packs/fractional_cto_v1/scoring.yaml`**: `minimum_threshold: 0`, `disqualifier_signals: {}` (empty for parity)
- **`app/services/readiness/scoring_constants.py`**: `from_pack()` returns `minimum_threshold`, `disqualifier_signals`; decay and suppressors from pack
- **`app/services/readiness/readiness_engine.py`**: `_check_disqualifier_signals()`; R=0 when disqualifier present; `disqualifiers_applied` in explain

### Phase 2 – Evidence & derivers

- **`signal_instances.evidence_event_ids`**: JSONB column; merge + deduplicate on upsert; pattern derivers
- **`app/packs/schemas.py`**: `ALLOWED_PATTERN_SOURCE_FIELDS` (title, summary, url, source)
- **`app/pipeline/deriver_engine.py`**: Filter source_fields by `ALLOWED_PATTERN_SOURCE_FIELDS`; evidence merge with `jsonb_agg(DISTINCT elem)`

### Phase 3 – Pack activation & API

- **`app/api/internal.py`**: `run_score`, `run_derive`, `run_ingest`, `run_update_lead_feed` accept optional `workspace_id`, `pack_id`; validates UUIDs
- **`alembic/versions/20260224_add_bookkeeping_pack.py`**: Inserts bookkeeping_v1 pack

### Phase 4 – ESL gate

- **`engagement_snapshots`**: `esl_decision`, `esl_reason_code`, `sensitivity_level`; backfill from explain
- **`job_runs.companies_esl_suppressed`**: Audit count for score jobs
- **`app/api/briefing.py`**, **`briefing_views.py`**: Filter suppressed companies; expose `esl_decision`, `sensitivity_level`

### Lead Feed (Issue #225)

- **`app/models/lead_feed.py`**: LeadFeed model
- **`app/services/lead_feed/`**: `build_lead_feed_from_snapshots`, `run_update_lead_feed`; projection builder
- **`alembic/versions/20260224_add_lead_feed_table.py`**: Creates lead_feed table; idempotent (handles existing table)
- **`alembic/versions/20260224_add_lead_feed_missing_columns.py`**: Adds missing columns when table exists with legacy schema

### Maintainer fixes

- Pack-scoped ingest; score_nightly pack filter; `companies_esl_suppressed` test assertion; multi-tenant briefing TODO

### Documentation

- **`docs/pipeline.md`**: run_score, run_derive, run_update_lead_feed API behavior
- **`docs/deriver-engine.md`**: Evidence type, source_fields whitelist
- **`docs/MULTI_TENANT_BRIEFING_TODO.md`**: Briefing workspace scoping when multi-workspace enabled

## Testing

- Phase 2: `test_from_pack_*`, `TestDisqualifierSignals`, parity harness; `test_deriver_evidence_*`, `test_deriver_evidence_merge_on_rerun`, `test_deriver_evidence_merge_handles_null_and_empty_existing`, `test_pattern_source_fields_url_and_source_preserved`, `test_pattern_matches_on_url_when_source_fields_includes_url`
- Phase 3/4: Pack resolution; ESL gate; briefing filters; `companies_esl_suppressed`
- Lead feed: `test_build_creates_rows_from_snapshots`, `test_build_excludes_suppressed_entities`, `test_build_isolates_by_workspace_and_pack`, `test_run_update_lead_feed_*`
- Maintainer: `test_run_ingest_daily_*`, `test_score_nightly`, `test_valid_token_calls_run_score_nightly`

## Verification

- [x] Fractional CTO behavior identical (parity tests)
- [x] evidence_event_ids merge + deduplicate; source_fields url/source preserved
- [x] run_update_lead_feed workspace/pack isolation verified
- [x] Ruff clean; Snyk zero issues on changed files

## References

- Plan: `.cursor/plans/scoring_engine_pack_refactor_ebb7e057.plan.md`
- Issues: #174, #175, #173, #225
