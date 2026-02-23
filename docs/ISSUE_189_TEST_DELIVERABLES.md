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

### Tests That Would Fail Without Production Code Changes (Future)

- `get_emerging_companies` does **not** yet filter by `pack_id` — when workspace.active_pack_id is implemented, a test asserting pack-scoped results would fail until the service is updated.
- ORE pipeline does **not** yet set `pack_id` on OutreachRecommendation — a test asserting rec.pack_id from ORE would fail until the pipeline is updated.

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
| **Regression (TRS→ESL→ORE)** | All `test_trs_esl_ore_pipeline.py` tests |
| **UI rendering** | `test_briefing_renders_emerging_companies_section`, `test_company_detail_renders_company_name` |

## 6. Snyk Security Scan

Snyk Code scan run on new/modified code:

- `app/models/signal_pack.py` — 0 issues
- `tests/test_issue_189_schema.py` — 0 issues
- `tests/test_issue_189_pack_isolation.py` — 0 issues
