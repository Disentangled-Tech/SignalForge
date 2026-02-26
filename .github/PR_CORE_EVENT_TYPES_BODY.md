# Core Event Types + Normalization (repo_activity, incorporation)

Closes #244
Closes #250

## Summary

Adds `repo_activity` and `incorporation` as core event types and updates normalization so core types are always accepted regardless of pack taxonomy. Packs that omit them store events but do not score them.

---

## Changes

### Core event types

- **`app/ingestion/event_types.py`**: Add `repo_activity` (#244), `incorporation` (#250) to `SIGNAL_EVENT_TYPES`

### Normalization

- **`app/ingestion/normalize.py`**: Update `_is_valid_event_type_for_pack` so core types are always accepted; pack taxonomy types also accepted when pack provided

### Other

- **`app/services/scoring.py`**: Fix `pack_id` type hint (UUID import + annotation)
- **`docs/ingestion-adapters.md`**: NewsAPI security note, GitHub cache config, Delaware/incorporation company resolution
- **`tests/test_analysis_record_pack_id.py`**: Skip `test_analyze_company_sets_pack_id` when `LLM_API_KEY` not set
- **`tests/test_signal_schemas.py`**: `test_normalize_accepts_core_type_when_pack_omits_it`

---

## Verification

- [x] `pytest tests/ -v -W error`
- [x] `ruff check` on modified files — clean
- [x] Legacy parity harness passes

## Risk

- **Low**: Additive; packs that omit core types accept events but do not score them
