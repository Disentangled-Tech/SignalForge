# Daily Signal Aggregation Job (Issue #246, Phase 1)

Closes #246

## Summary

Adds a unified daily aggregation job that orchestrates ingest → derive → score. Single entry point for cron. Preserves fractional CTO flow; no changes to existing stage implementations.

### Phases Implemented

1. **Phase 1 — Daily aggregation orchestrator**: `run_daily_aggregation(db, workspace_id, pack_id)` in `app/services/aggregation/daily_aggregation.py`; stage in `STAGE_REGISTRY`; `POST /internal/run_daily_aggregation`; CLI script; `make signals-daily`

---

## Changes

### Orchestrator

- **`app/services/aggregation/daily_aggregation.py`** (new): Calls `run_ingest_daily` → `run_deriver` → `run_score_nightly`; resolves pack via `pack_id or get_pack_for_workspace(workspace_id) or get_default_pack_id(db)`; on success calls `get_emerging_companies` for ranked list; logs ranked companies (name, composite, band) to console; creates `JobRun` with `job_type="daily_aggregation"` for audit

### Pipeline

- **`app/pipeline/stages.py`**: Add `_daily_aggregation_stage` to `STAGE_REGISTRY` with key `"daily_aggregation"`
- **`app/pipeline/executor.py`**: Extend `_cached_result` for `job_type="daily_aggregation"` (return shape compatible with API)

### API

- **`app/api/internal.py`**: Add `POST /internal/run_daily_aggregation` with `workspace_id`, `pack_id` query params; `X-Internal-Token`; `X-Idempotency-Key` support. Returns `status`, `job_run_id`, `inserted`, `companies_scored`, `ranked_count`, `error`

### CLI & Makefile

- **`scripts/run_daily_aggregation.py`** (new): CLI script; get db session, call `run_daily_aggregation`, print result
- **`Makefile`**: Add `signals-daily` target

### Tests

- **`tests/test_daily_aggregation.py`** (new): Unit tests — calls stages in order; provider failure non-fatal; no duplicates on rerun; ranked output shape; workspace/pack passed to stages; JobRun created
- **`tests/test_internal.py`**: Add `TestRunDailyAggregation` — returns expected shape, requires token, wrong token 403

---

## Configuration

No new env vars. Uses existing `INTERNAL_JOB_TOKEN` for API auth. Optional `workspace_id` and `pack_id` query params (defaults used when omitted).

---

## Verification

- [x] `pytest tests/test_daily_aggregation.py tests/test_internal.py tests/test_pipeline.py tests/test_legacy_pack_parity.py tests/test_ingestion_scoring_integration.py -v -W error`
- [x] `ruff check` on modified files — clean
- [x] Snyk code scan: 0 issues
- [x] Legacy parity harness passes

---

## Cron Recommendation

After merge, cron can call:

- **Option A (unified)**: `POST /internal/run_daily_aggregation` once per day (recommended)
- **Option B (granular)**: `POST /internal/run_ingest` (hourly) + `POST /internal/run_derive` + `POST /internal/run_score` (daily)

---

## Risk

- **Low**: Additive; fractional CTO flow unchanged
- **Idempotency**: Uses `job_type="daily_aggregation"`; idempotency key is workspace-scoped
