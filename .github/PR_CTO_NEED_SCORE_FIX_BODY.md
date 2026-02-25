# cto_need_score Pack Scoping Fix

References https://github.com/Disentangled-Tech/SignalForge/issues/239 (follow-up)

## Summary

The `company_detail` view calculated a score using the workspace's active pack and called `score_company()` to persist it. `score_company()` unconditionally updated `company.cto_need_score` and `company.current_stage`, which should only cache the **default pack's** values. When viewing a company with a non-default workspace pack, this corrupted `cto_need_score` with a workspace-specific score, breaking backward compatibility and causing inconsistent display scores.

## Changes

### `score_company()` (`app/services/scoring.py`)
- Added `pack_id: UUID | None = None` parameter
- Only persists to `company.cto_need_score` and `company.current_stage` when `pack_id is None` or `pack_id == get_default_pack_id(db)` (both gated for consistency)
- Docstring updated to reflect behavior

### Call sites
- **`app/api/views.py`**: Repair path only runs when `pack_id == default_pack_id`; passes `pack_id` to `score_company`
- **`app/services/scan_orchestrator.py`**: Passes `pack_id` to `score_company` in `run_scan_company_full` and `run_scan_company_with_job`

### Tests
- **`tests/test_scoring.py`**: `test_does_not_persist_cto_need_score_when_non_default_pack`, `test_persists_cto_need_score_when_default_pack`; mocks updated for `get_default_pack_id` / `resolve_pack`
- **`tests/test_views.py`**: `test_detail_repair_path_skipped_when_non_default_pack`
- **`tests/test_scan_orchestrator.py`**: Assertion updated for `score_company(..., pack_id=pack_uuid)`

## Verification

- [x] `pytest tests/test_scoring.py tests/test_scan_orchestrator.py tests/test_views.py -v -W error`
- [x] `ruff check` on modified files — clean
- [x] Snyk — zero issues on scoring.py

## Risk

- **Low**: Additive parameter; backward compatible when `pack_id` not passed (persists as before)
