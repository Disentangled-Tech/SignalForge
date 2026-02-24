# Phase 3: Pack Activation Runtime (Closes #174)

## Summary

Implements Phase 3 of the scoring engine pack refactor: wires `workspace_id` → `Workspace.active_pack_id` → pack resolution in score/derive stages. Fallback to default pack when workspace has no active pack.

## Changes

### Pack resolution
- **`app/services/pack_resolver.py`**: `get_pack_for_workspace(db, workspace_id)` — returns `Workspace.active_pack_id` when set, else `get_default_pack_id(db)`

### Pipeline wiring
- **`app/pipeline/executor.py`**: When `pack_id` is None, use `get_pack_for_workspace(db, ws_id)` instead of `get_default_pack_id(db)`
- **`app/services/readiness/score_nightly.py`**: When `pack_id` is None and `workspace_id` provided, resolve pack via `get_pack_for_workspace`

### API
- **`app/api/internal.py`**: `POST /internal/run_score` accepts optional `workspace_id` and `pack_id` query params; validates UUIDs, returns 422 for invalid values

### Critical fixes
- **`_parse_uuid_or_422()`**: Validates `workspace_id` and `pack_id` before use; returns 422 with clear message for malformed UUIDs

### Documentation
- **`docs/pipeline.md`**: Documents `run_score` query params and validation behavior
- **`docs/ISSUE_LEGACY_PACK_PARITY_HARNESS.md`**: Updated follow-up checklist

### Tests
- **`tests/test_pack_resolver.py`**: 4 tests for `get_pack_for_workspace`
- **`tests/test_pipeline.py`**: `test_run_stage_score_uses_workspace_active_pack_when_pack_id_omitted`
- **`tests/test_internal.py`**: `test_run_score_with_workspace_and_pack_params`, `test_run_score_invalid_workspace_id_returns_422`, `test_run_score_invalid_pack_id_returns_422`
- **`tests/test_score_nightly.py`**: `test_run_score_nightly_with_workspace_id_uses_workspace_active_pack`
- **`tests/test_legacy_pack_parity.py`**: `test_get_emerging_companies_pack_returns_companies_with_snapshots`

## Verification

- [x] Fractional CTO behavior unchanged (default workspace has `active_pack_id` from migration)
- [x] All tests pass with `-W error`
- [x] Ruff clean; Snyk zero issues on changed files
- [x] Maintainer review: Safe to merge

## References

- Plan: `.cursor/plans/scoring_engine_pack_refactor_ebb7e057.plan.md`
- Issue: #174
