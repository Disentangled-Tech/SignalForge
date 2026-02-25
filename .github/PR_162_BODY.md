# Validate and Implement Scan All — Phases 0–4 + Ingestion Adapters

Closes https://github.com/Disentangled-Tech/SignalForge/issues/162
Closes https://github.com/Disentangled-Tech/SignalForge/issues/134
Closes https://github.com/Disentangled-Tech/SignalForge/issues/210

## Summary

Implements the full Scan All validation and Pack Architecture migration roadmap from `.cursor/plans/validate_and_implement_scan_all_250f0fdc.plan.md`, plus Crunchbase and Product Hunt ingestion adapters from `.cursor/plans/crunchbase_product_hunt_ingestion_adapters_85eab9c2.plan.md`:

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
- **views.py**: `workspace_id` filtering in `companies_list`, `companies_scan_all`, `company_rescan` (multi-tenant readiness)
- **Tests**: `test_run_scan_all_sets_pack_id_when_available`, `test_creates_job_run_with_pack_id_when_available`, `test_rescan_creates_job_run_with_pack_id_and_workspace_id`, `TestWorkspaceIdFiltering` (8 tests for workspace_id filtering)

### Phase 4 (Cleanup)
- **views.py**: Company detail repair path passes `pack=pack` to `score_company`
- **docs/pipeline.md**: New "Scan vs Ingest/Derive/Score" section
- **Tests**: `test_detail_repair_path_calls_score_company_with_pack`

### Ingest UX (Run Ingest surfaces 0 companies)
- **settings_views.py**: When latest ingest completes with 0 processed, show "Why 0 new companies?" info box
- **settings/index.html**: Prominent blue callout explaining no adapters configured or APIs returned empty
- **Tests**: `test_run_ingest_daily_test_adapter_takes_precedence`

### Ingestion Adapters (Issues #134, #210)
- **app/ingestion/adapters/**: `CrunchbaseAdapter`, `ProductHuntAdapter` (env-gated)
- **ingest_daily.py**: `_get_adapters()` returns Crunchbase when `INGEST_CRUNCHBASE_ENABLED=1` and `CRUNCHBASE_API_KEY` set; Product Hunt when `INGEST_PRODUCTHUNT_ENABLED=1` and `PRODUCTHUNT_API_TOKEN` set
- **docs/pipeline.md**: "Ingestion Adapters" section; link to `ingestion-adapters.md`
- **Tests**: `test_run_ingest_daily_uses_crunchbase_when_configured`, `test_run_ingest_daily_uses_producthunt_when_configured`, `test_run_ingest_daily_test_adapter_takes_precedence`, `test_run_ingest_daily_uses_both_adapters_when_both_configured`

## Verification

- [x] `pytest tests/ -v -W error -m 'not integration'` — 1171 passed
- [x] `ruff check` on modified files — clean
- [x] Fractional CTO behavior unchanged (pack interfaces extract same weights)
- [x] No new migrations (JobRun.pack_id already exists)

## Risk

- **Low**: All changes additive; pack parameter optional with fallback
- **Alembic**: Removed duplicate migration files (`* 2.py`) that caused multiple heads
