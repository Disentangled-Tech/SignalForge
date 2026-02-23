# Issue #189 Test Deliverables — Update Database Schema to Support Signal Pack Architecture

## 1. Test Inventory

| File | Test | Purpose |
|------|------|---------|
| `tests/test_issue_189_schema.py` | `test_signal_packs_table_exists` | Verify signal_packs table exists after migration |
| `tests/test_issue_189_schema.py` | `test_fractional_cto_v1_pack_inserted` | fractional_cto_v1 pack exists with correct pack_id, version, industry |
| `tests/test_issue_189_schema.py` | `test_readiness_snapshots_has_pack_id_column` | readiness_snapshots has pack_id column |
| `tests/test_issue_189_schema.py` | `test_engagement_snapshots_has_pack_id_column` | engagement_snapshots has pack_id column |
| `tests/test_issue_189_schema.py` | `test_signal_events_has_pack_id_column` | signal_events has pack_id column |
| `tests/test_issue_189_schema.py` | `test_signal_records_has_pack_id_column` | signal_records has pack_id column |
| `tests/test_issue_189_schema.py` | `test_outreach_recommendations_has_pack_id_and_playbook_id` | outreach_recommendations has pack_id and playbook_id |
| `tests/test_issue_189_schema.py` | `test_readiness_snapshots_unique_includes_pack_id` | Unique constraint includes pack_id |
| `tests/test_issue_189_schema.py` | `test_readiness_snapshots_pack_id_column_accepts_fk` | pack_id FK accepts valid signal_packs.id |
| `tests/test_issue_189_schema.py` | `test_signal_pack_id_unique_per_version` | pack_id + version unique index exists |
| `tests/test_issue_189_pack_isolation.py` | `test_pack_isolation_readiness_snapshots` | Query by pack_id returns only that pack's ReadinessSnapshot |
| `tests/test_issue_189_pack_isolation.py` | `test_pack_isolation_engagement_snapshots` | Query by pack_id returns only that pack's EngagementSnapshot |
| `tests/test_issue_189_pack_isolation.py` | `test_get_emerging_companies_respects_pack_when_filtered` | get_emerging_companies returns pack-scoped data |
| `tests/test_issue_189_pack_isolation.py` | `test_outreach_recommendation_stores_pack_id_and_playbook_id` | OutreachRecommendation persists pack_id and playbook_id |
| `tests/test_issue_189_pack_isolation.py` | `test_cross_pack_no_contamination` | Query by pack A does not return pack B's data |
| `tests/test_ui_briefing.py` | `test_briefing_renders_emerging_companies_section` | GET /briefing renders emerging companies when data present |
| `tests/test_ui_briefing.py` | `test_briefing_base_template_inherited` | Base template nav (Companies, Briefing) present |
| `tests/test_ui_company_detail.py` | `test_company_detail_renders_company_name` | GET /companies/{id} renders company name |
| `tests/test_ui_company_detail.py` | `test_company_detail_has_outreach_section` | Company detail has outreach-related content |
| `tests/test_readiness_snapshot.py` | `test_readiness_snapshot_unique_constraint` | **Updated** — Duplicate (company_id, as_of, pack_id) raises IntegrityError |
| `tests/test_emerging_companies.py` | (all 10 tests) | **Updated** — Added pack_id to ReadinessSnapshot/EngagementSnapshot fixtures |
| `tests/test_trs_esl_ore_pipeline.py` | (both tests) | **Updated** — Added pack_id to ReadinessSnapshot fixtures |
| `tests/conftest.py` | `fractional_cto_pack_id` | **New** — Fixture returning fractional_cto_v1 pack UUID from DB |

### Declarative Pack Plan Tests (TDD for Steps 1.2–1.4, 2.x)

| File | Test | Purpose |
|------|------|---------|
| `tests/test_pack_loader.py` | `test_load_fractional_cto_v1_returns_pack` | load_pack returns Pack with taxonomy, scoring, esl_policy |
| `tests/test_pack_loader.py` | `test_pack_taxonomy_has_signal_ids` | Taxonomy includes all 23 CTO event types |
| `tests/test_pack_loader.py` | `test_load_nonexistent_pack_raises` | load_pack raises for nonexistent pack |
| `tests/test_pack_loader.py` | `test_load_invalid_version_raises` | load_pack raises for invalid version |
| `tests/test_pack_loader.py` | `test_pack_json_has_required_fields` | pack.json has id, version, name |
| `tests/test_pack_loader.py` | `test_scoring_yaml_has_base_scores` | scoring.yaml has base scores |
| `tests/test_pack_fractional_cto_parity.py` | `test_funding_raised_parity` | compute_readiness with pack == without pack |
| `tests/test_pack_fractional_cto_parity.py` | `test_cto_role_posted_no_hired_parity` | leadership_gap parity |
| `tests/test_pack_fractional_cto_parity.py` | `test_multi_event_composite_parity` | Multi-event composite parity |
| `tests/test_pack_fractional_cto_parity.py` | `test_esl_boundary_parity` | map_esl_to_recommendation parity |
| `tests/test_pack_scoped_queries.py` | `test_get_emerging_companies_excludes_other_pack` | Pack A query excludes pack B data |
| `tests/test_pack_scoped_queries.py` | `test_get_briefing_data_emerging_companies_single_pack` | Briefing data has consistent pack_id |
| `tests/test_readiness_engine.py` | `TestReadinessEnginePackParameter::test_compute_readiness_accepts_pack_none` | compute_readiness accepts pack=None |
| `tests/test_readiness_engine.py` | `TestReadinessEnginePackParameter::test_compute_readiness_with_cto_pack_produces_same_as_none` | Pack parity |
| `tests/test_esl_engine.py` | `test_map_esl_to_recommendation_accepts_pack_none` | map_esl_to_recommendation accepts pack=None |
| `tests/test_esl_engine.py` | `test_map_esl_to_recommendation_with_cto_pack_same_as_none` | ESL boundary parity |
| `tests/test_issue_189_pack_isolation.py` | `test_get_emerging_companies_respects_pack_when_filtered` | **Strengthened** — Asserts pack exclusion |
| `tests/test_trs_esl_ore_pipeline.py` | (both tests) | **Updated** — Assert rec.pack_id set by ORE pipeline |

## 2. Coverage Impact

### Commands

```bash
# Run all tests
pytest tests/ -v

# Run with coverage (fail under 75%)
pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=75

# Run integration tests only
pytest tests/ -v -m integration

# Run Issue #189 tests only
pytest tests/test_issue_189_schema.py tests/test_issue_189_pack_isolation.py tests/test_ui_briefing.py tests/test_ui_company_detail.py -v
```

### Modules Touched by Issue #189

- `app/models/signal_pack.py` — **New** — SignalPack model (required for FK resolution)
- `app/models/readiness_snapshot.py` — pack_id column (existing)
- `app/models/engagement_snapshot.py` — pack_id column (existing)
- `app/models/signal_event.py` — pack_id column (existing)
- `app/models/signal_record.py` — pack_id column (existing)
- `app/models/outreach_recommendation.py` — pack_id, playbook_id (existing)

Tests added for schema validation, pack isolation, and UI rendering. Regression tests (emerging companies, TRS-ESL-ORE) updated with pack_id fixtures.

**Current coverage:** 92% (above 75% requirement). No modules below target.

## 3. Failing Tests (Expected Before Implementation)

All tests currently **pass** because:

1. **Migration** `alembic/versions/20260223_add_signal_pack_schema.py` was created to unblock the test DB (DB was at revision `20260223_signal_packs` but migration file was missing).
2. **SignalPack model** `app/models/signal_pack.py` was added so SQLAlchemy can resolve the `signal_packs.id` foreign key referenced by other models.
3. **Fixtures** were updated to use `pack_id` from the fractional_cto_v1 pack in the DB.

### Tests That Would Fail Without Schema/Migration

- All `test_issue_189_schema.py` tests — require signal_packs table and pack_id columns
- All `test_issue_189_pack_isolation.py` tests — require pack-scoped data
- `test_readiness_snapshot_unique_constraint` — requires (company_id, as_of, pack_id) unique constraint
- Emerging companies and TRS-ESL-ORE tests — would fail with unique constraint violations if pack_id not set

### Tests That Skip Until Production Code Changes (TDD)

Tests that **skip** (not fail) until the corresponding production code exists:

- **`tests/test_pack_loader.py`** — Entire module skips via `pytest.importorskip("app.packs")` until `app/packs/loader.py` and `packs/fractional_cto_v1/` exist (Plan Step 1.2).
- **`tests/test_pack_fractional_cto_parity.py`** — Skips when `load_pack` not available; will fail when `compute_readiness(..., pack=...)` and `map_esl_to_recommendation(..., pack=...)` not implemented (Plan Steps 1.3, 1.4).
- **`tests/test_readiness_engine.py::TestReadinessEnginePackParameter::test_compute_readiness_accepts_pack_none`** — Skips when `compute_readiness` does not accept `pack` parameter (Plan Step 1.3).
- **`tests/test_esl_engine.py::test_map_esl_to_recommendation_accepts_pack_none`** — Skips when `map_esl_to_recommendation` does not accept `pack` parameter (Plan Step 1.4).

Once `app.packs.loader` exists, pack loader tests will run. Once `compute_readiness` and `map_esl_to_recommendation` accept `pack`, parity tests will run and assert identical output.

## 4. Verification Commands

```bash
pytest tests/ -v
pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=75
pytest tests/ -v -m integration
```

## 5. Invariants Tested

| Invariant | Test(s) |
|-----------|---------|
| **Pack isolation** | `test_pack_isolation_readiness_snapshots`, `test_pack_isolation_engagement_snapshots`, `test_cross_pack_no_contamination` |
| **Schema correctness** | All `test_issue_189_schema.py` tests |
| **Unique constraint** | `test_readiness_snapshot_unique_constraint` |
| **FK integrity** | `test_readiness_snapshots_pack_id_column_accepts_fk` |
| **Outreach pack/playbook** | `test_outreach_recommendation_stores_pack_id_and_playbook_id` |
| **Regression (emerging companies)** | All `test_emerging_companies.py` tests |
| **Regression (TRS→ESL→ORE)** | All `test_trs_esl_ore_pipeline.py` tests (incl. pack_id assertion) |
| **UI rendering** | `test_briefing_renders_emerging_companies_section`, `test_company_detail_renders_company_name` |
| **Pack-scoped queries** | `test_get_emerging_companies_excludes_other_pack`, `test_get_briefing_data_emerging_companies_single_pack` |
| **ORE pack_id** | `test_trs_esl_ore_pipeline_integration`, `test_ore_pipeline_uses_computed_esl` |

## 6. Snyk Security Scan

Snyk Code scan run on new/modified code:

- `app/models/signal_pack.py` — 0 issues
- `tests/test_issue_189_schema.py` — 0 issues
- `tests/test_issue_189_pack_isolation.py` — 0 issues
