# Validate and Implement Scan All — Phases 0–4

Closes https://github.com/Disentangled-Tech/SignalForge/issues/162

## Summary

Implements the full Scan All validation and Pack Architecture migration roadmap from `.cursor/plans/validate_and_implement_scan_all_250f0fdc.plan.md`:

- **Phase 0**: Fix Issue #162 — validate Scan All, improve empty-state UX
- **Phase 1**: Engine abstraction — `PackScoringInterface`, `PackAnalysisInterface`
- **Phase 2**: CTO pack extraction — scan passes pack to `analyze_company` / `score_company`
- **Phase 3**: Pack activation runtime — `JobRun.pack_id` for audit
- **Phase 4**: Cleanup — company detail repair passes pack; docs update

## Changes

### Phase 0 (Issue #162)
- **scan_orchestrator**: When no companies have `website_url`, set `job.error_message` with actionable guidance; job completes (not failed)
- **settings/index.html**: Improved empty-state: "Add a company with a website URL, then run Scan All from the Companies page"
- **Tests**: `test_run_scan_all_no_companies_with_url_sets_error_message`, `test_run_scan_all_with_url_processes_and_updates_job`

### Phase 1 (Engine abstraction)
- **app/packs/interfaces.py**: `PackScoringInterface`, `PackAnalysisInterface`, adapters
- **scoring.py**: Uses `adapt_pack_for_scoring`; `_get_weights_from_pack` takes interface
- **analysis.py**: Accepts optional `pack` parameter (Phase 1: unused)
- **Tests**: `test_pack_interfaces.py`, `test_accepts_pack_parameter_unchanged_behavior`

### Phase 2 (CTO pack extraction)
- **scan_orchestrator**: Resolves pack via `get_default_pack(db)`; passes to `analyze_company` / `score_company`
- **run_scan_all**: Passes pack to `run_scan_company_full` to avoid per-company resolution
- **run_scan_company_full**: Accepts optional `pack`; uses when provided

### Phase 3 (Pack activation)
- **JobRun**: `pack_id` and `workspace_id` set when creating scan and company_scan jobs (audit trail)
- **scan_orchestrator**: `run_scan_all`, `run_scan_company_with_job` set `workspace_id=UUID(DEFAULT_WORKSPACE_ID)`
- **views.py company_rescan**: Sets `pack_id` and `workspace_id` on JobRun for audit consistency
- **Tests**: `test_run_scan_all_sets_pack_id_when_available`, `test_creates_job_run_with_pack_id_when_available`, `test_rescan_creates_job_run_with_pack_id_and_workspace_id`

### Phase 4 (Cleanup)
- **views.py**: Company detail repair path passes `pack=pack` to `score_company`
- **docs/pipeline.md**: New "Scan vs Ingest/Derive/Score" section
- **Tests**: `test_detail_repair_path_calls_score_company_with_pack`

## Verification

- [x] `pytest tests/ -v -W error -m 'not integration'` — 211 passed
- [x] `ruff check` on modified files — clean
- [x] Fractional CTO behavior unchanged (pack interfaces extract same weights)
- [x] No new migrations (JobRun.pack_id already exists)

## Risk

- **Low**: All changes additive; pack parameter optional with fallback
- **Pre-existing**: Alembic multiple heads may block integration tests until resolved
