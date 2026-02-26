# GitHub Provider + REPO_ACTIVITY (Issue #244)

Closes #244

## Summary

Adds the GitHub ingestion adapter and REPO_ACTIVITY as a core event type, with optional pack adoption for fractional_cto_v1. Implements Phases 1–4 of the approved plan.

1. **Phase 1 — REPO_ACTIVITY core event type**: Add `repo_activity` to `SIGNAL_EVENT_TYPES`; core types always accepted regardless of pack taxonomy.
2. **Phase 2 — GitHub adapter + ingest wiring**: `GitHubAdapter` fetches repo/org events; wired when `INGEST_GITHUB_ENABLED=1` and `GITHUB_TOKEN` set.
3. **Phase 3 — Company resolution for GitHub**: Adapter fetches org metadata (`blog`/`html_url`) to populate `website_url` for company resolution.
4. **Phase 4 — Documentation + pack adoption**: GitHub section in `docs/ingestion-adapters.md`; `repo_activity` added to fractional_cto_v1 (taxonomy, derivers, scoring).

---

## Changes

### Core event type (Phase 1)

- **`app/ingestion/event_types.py`**: Add `repo_activity` to `SIGNAL_EVENT_TYPES`
- **`app/ingestion/normalize.py`**: `_is_valid_event_type_for_pack` — core types always accepted; pack taxonomy types also accepted when pack provided
- **`tests/test_event_types.py`**, **`tests/test_signal_schemas.py`**, **`tests/test_pack_loader.py`**: Tests for core type and normalization

### GitHub adapter (Phase 2)

- **`app/ingestion/adapters/github_adapter.py`** (new): Fetches repo/org events; maps to `RawEvent` with `event_type_candidate='repo_activity'`
- **`app/ingestion/adapters/__init__.py`**: Export `GitHubAdapter`
- **`app/services/ingestion/ingest_daily.py`**: Wire when `INGEST_GITHUB_ENABLED=1` and `GITHUB_TOKEN`/`GITHUB_PAT` set
- **`tests/test_github_adapter.py`** (new): Unit tests
- **`tests/test_ingest_daily.py`**: GitHub env-gating and wiring tests

### Company resolution (Phase 3)

- **`app/ingestion/adapters/github_adapter.py`**: Fetches org metadata (`GET /orgs/{org}`) for `blog`/`html_url`; populates `website_url` in `RawEvent`
- **`tests/test_ingestion_adapter.py`**: `test_run_ingest_github_stores_signal_event_with_company_id`

### Documentation + pack adoption (Phase 4)

- **`docs/ingestion-adapters.md`**: GitHub section (API token, config, env vars, rate limits, security, event mapping)
- **`packs/fractional_cto_v1/taxonomy.yaml`**: Add `repo_activity` to signal_ids, dimensions.C, labels, explainability_templates
- **`packs/fractional_cto_v1/derivers.yaml`**: Passthrough `repo_activity` → `repo_activity`
- **`packs/fractional_cto_v1/scoring.yaml`**: `complexity.repo_activity: 15`
- **`tests/test_legacy_pack_parity.py`**: Parity test allows pack superset (repo_activity)
- **`tests/test_readiness_engine.py`**: `test_repo_activity_contributes_to_complexity`

---

## Configuration

```bash
export GITHUB_TOKEN=your-token
export INGEST_GITHUB_ENABLED=1
export INGEST_GITHUB_REPOS=owner/repo1,owner/repo2   # and/or
export INGEST_GITHUB_ORGS=org1,org2
```

`GITHUB_PAT` is also accepted. At least one of `INGEST_GITHUB_REPOS` or `INGEST_GITHUB_ORGS` is required.

---

## Verification

- [x] `pytest tests/test_legacy_pack_parity.py tests/test_readiness_engine.py tests/test_pack_loader.py tests/test_event_types.py tests/test_signal_schemas.py tests/test_github_adapter.py tests/test_ingest_daily.py tests/test_ingestion_adapter.py -v -W error`
- [x] `ruff check` on modified files — clean
- [x] Snyk code scan: 0 issues on changed Python files
- [x] Legacy parity harness passes

## Risk

- **Low**: Additive; fractional CTO flow unchanged
- **Pack adoption**: Companies with `repo_activity` events get higher Complexity when using fractional_cto_v1
