# Phases 2–4: CTO Pack Extraction, Pack Activation, ESL Gate + Maintainer Fixes

Closes #174, #175, #173

## Summary

Implements Phases 2–4 of the scoring engine pack refactor plus maintainer-requested fixes:

- **Phase 2**: `minimum_threshold`, `disqualifier_signals`, parity harness; `evidence_event_ids` on signal_instances; pattern derivers
- **Phase 3**: Pack activation runtime; `workspace_id`/`pack_id` on run_score, run_derive, run_ingest; bookkeeping_v1 pack
- **Phase 4**: ESL decision gate (`esl_decision`, `esl_reason_code`, `sensitivity_level`); briefing filters suppressed companies; `companies_esl_suppressed` audit
- **Maintainer fixes**: Pack-scoped ingest, score_nightly pack filter, `companies_esl_suppressed` test assertion, multi-tenant briefing TODO

## Changes

### Phase 2 – Pack config & scoring
- **`packs/fractional_cto_v1/scoring.yaml`**: `minimum_threshold: 0`, `disqualifier_signals: {}` (empty for parity)
- **`app/services/readiness/scoring_constants.py`**: `from_pack()` returns `minimum_threshold`, `disqualifier_signals`; decay and suppressors from pack
- **`app/services/readiness/readiness_engine.py`**: `_check_disqualifier_signals()`; R=0 when disqualifier present; `disqualifiers_applied` in explain

### Phase 2 – Evidence & derivers
- **`signal_instances.evidence_event_ids`**: JSONB column; merge on upsert; pattern derivers; schema validation for `source_fields`, decay, suppressors, ESL policy
- **`app/packs/schemas.py`**: `ALLOWED_PATTERN_SOURCE_FIELDS` comment aligned with implementation (title, summary, url, source)

### Phase 3 – Pack activation & API
- **`app/services/pack_resolver.py`**: `get_pack_for_workspace()` logs warning when workspace not found
- **`app/api/internal.py`**: `run_score`, `run_derive`, `run_ingest` accept optional `workspace_id`, `pack_id`; validates UUIDs; documents ingest pack behavior
- **`alembic/versions/20260224_add_bookkeeping_pack.py`**: Inserts bookkeeping_v1 pack (blocked_signals: financial_distress)

### Phase 4 – ESL gate
- **`engagement_snapshots`**: `esl_decision`, `esl_reason_code`, `sensitivity_level`; backfill from explain
- **`job_runs.companies_esl_suppressed`**: Audit count for score jobs
- **`app/api/briefing.py`**, **`briefing_views.py`**: Filter suppressed companies; expose `esl_decision`, `sensitivity_level`

### Maintainer fixes (required & suggested)
- **Pack-scoped ingest**: `run_ingest` accepts optional `pack_id`; `run_ingest_daily` resolves pack and passes to `run_ingest`; ingested events written to resolved pack
- **score_nightly**: `ids_from_events` filters by pack when `resolved_pack_id` is set (reduces iteration over companies with no events for the pack)
- **Test**: `test_valid_token_calls_run_score_nightly` asserts `companies_esl_suppressed` in response
- **Briefing**: TODO added for multi-tenant workspace scoping when enabled

### Documentation
- **`docs/MINIMUM_THRESHOLD_ENFORCEMENT.md`**: Where `minimum_threshold` is stored and enforced
- **`docs/ISSUE_LEGACY_PACK_PARITY_HARNESS.md`**: Parity harness must pass before merge
- **`docs/pipeline.md`**: Pipeline stages and API behavior
- **`docs/deriver-engine.md`**: Evidence type (integers), source_fields whitelist

## Testing

- Phase 2: `test_from_pack_*`, `TestDisqualifierSignals`, parity harness; `test_deriver_evidence_*`, `test_deriver_evidence_merge_handles_null_and_empty_existing`
- Phase 3: Pack resolution; run_derive/run_ingest with workspace_id/pack_id
- Phase 4: ESL gate; briefing filters; `companies_esl_suppressed`
- Maintainer: `test_run_ingest_daily_*` (pack_id passed to run_ingest); `test_score_nightly` (pack filter); `test_valid_token_calls_run_score_nightly` (companies_esl_suppressed)

## Verification

- [x] Fractional CTO behavior identical (parity tests)
- [x] Workspace-not-found logged; API consistent across run_score/run_derive/run_ingest
- [x] evidence_event_ids merge handles NULL/empty existing
- [x] Ingest writes events to resolved pack (not always default)
- [x] Ruff clean; Snyk zero issues on changed files

## References

- Plan: `.cursor/plans/scoring_engine_pack_refactor_ebb7e057.plan.md`
- Issues: #174, #175, #173
