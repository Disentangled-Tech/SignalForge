# NewsAPI Adapter + REPO_ACTIVITY Core Event Type

Closes https://github.com/Disentangled-Tech/SignalForge/issues/245
Closes https://github.com/Disentangled-Tech/SignalForge/issues/244

## Summary

Two changes in one PR:

1. **NewsAPI ingestion adapter** (Issue #245): Adds NewsAPI.org as an ingestion adapter for funding-related news articles.
2. **REPO_ACTIVITY core event type** (Issue #244 Phase 1): Adds `repo_activity` to core event types and updates normalization so core types are always accepted regardless of pack taxonomy.

---

## 1. NewsAPI Adapter (Issue #245)

### Changes

- **`app/ingestion/adapters/newsapi_adapter.py`** (new): NewsAPIAdapter with keyword-based search, company name heuristics, pagination, rate-limit handling. Emits `RawEvent` with `event_type_candidate='funding_raised'`.
- **`app/ingestion/adapters/__init__.py`**: Export NewsAPIAdapter
- **`app/services/ingestion/ingest_daily.py`**: Wire NewsAPI when `INGEST_NEWSAPI_ENABLED=1` and `NEWSAPI_API_KEY` set
- **`docs/ingestion-adapters.md`**: NewsAPI section with security note (API key in URL; avoid logging full request URLs)
- **`tests/test_newsapi_adapter.py`** (new): Unit tests for adapter behavior
- **`tests/test_ingest_daily.py`**: NewsAPI env-gating and run_ingest_daily wiring tests

### Configuration

```bash
export NEWSAPI_API_KEY=your-api-key
export INGEST_NEWSAPI_ENABLED=1
```

Optional: `INGEST_NEWSAPI_KEYWORDS` (comma-separated) or `INGEST_NEWSAPI_KEYWORDS_JSON` (JSON array).

---

## 2. REPO_ACTIVITY Core Event Type (Issue #244 Phase 1)

### Changes

- **`app/ingestion/event_types.py`**: Add `repo_activity` to `SIGNAL_EVENT_TYPES`
- **`app/ingestion/normalize.py`**: Update `_is_valid_event_type_for_pack` so core types are always accepted regardless of pack. Pack taxonomy types are also accepted when pack is provided.
- **`tests/test_event_types.py`** (new): `test_repo_activity_is_valid_event_type`
- **`tests/test_signal_schemas.py`**: `test_normalize_accepts_repo_activity_without_pack`, `test_normalize_accepts_core_type_when_pack_omits_it`; shared `_mock_pack` helper
- **`tests/test_pack_loader.py`**: Update `test_pack_taxonomy_has_signal_ids` to assert pack taxonomy ids are valid core types (packs not required to adopt all core types)

---

## Verification

- [x] `pytest tests/ -v -W error`
- [x] `pytest tests/ -v --cov=app --cov-fail-under=75 -W error`
- [x] `ruff check` on modified files — clean
- [x] Snyk code scan: 0 issues on changed files
- [x] Legacy parity harness passes

## Risk

- **Low**: Additive; no changes to existing adapters; fractional CTO behavior unchanged
- **REPO_ACTIVITY**: Packs that omit `repo_activity` from taxonomy will now accept it (core type); events stored but not scored until pack adopts it
