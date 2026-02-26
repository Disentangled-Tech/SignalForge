# Delaware Socrata Adapter + Incorporation Core Event Type (Issue #250)

Closes #250

## Summary

Adds the Delaware Socrata ingestion adapter and `incorporation` as a core event type. Incorporation is core platform infrastructure—not specific to any pack. fractional_cto_v1 does **not** adopt incorporation; events are stored but not scored by that pack.

### Phases Implemented

1. **Phase 1 — Core event type + adapter**: `incorporation` in `SIGNAL_EVENT_TYPES`; `DelawareSocrataAdapter` fetches filings from Delaware Open Data (Socrata SODA API); wired in `ingest_daily.py`
2. **Phase 4 — Cleanup**: Documentation finalized (dataset IDs, SoQL examples); implementation summary; Snyk scan clean

---

## Changes

### Core event type

- **`app/ingestion/event_types.py`**: Add `incorporation` to `SIGNAL_EVENT_TYPES`
- **`app/ingestion/normalize.py`**: Core types always accepted (existing behavior)

### Delaware Socrata adapter

- **`app/ingestion/adapters/delaware_socrata_adapter.py`** (new): Fetches incorporation filings via SODA API; maps to `RawEvent` with `event_type_candidate='incorporation'`; validates `INGEST_DELAWARE_SOCRATA_DATE_COLUMN` (alphanumeric/underscore only) to prevent SoQL injection
- **`app/ingestion/adapters/__init__.py`**: Export `DelawareSocrataAdapter`
- **`app/services/ingestion/ingest_daily.py`**: Wire when `INGEST_DELAWARE_SOCRATA_ENABLED=1` and `INGEST_DELAWARE_SOCRATA_DATASET_ID` set

### Documentation

- **`docs/ingestion-adapters.md`**: Delaware Socrata section (dataset IDs, SoQL examples, rate limits, event mapping, company resolution)
- **`docs/implementation-plan-delaware-incorporation-issue-250.md`** (new): Implementation summary and verification

### Tests

- **`tests/test_delaware_socrata_adapter.py`** (new): Unit tests
- **`tests/test_ingest_daily.py`**: Delaware env-gating and wiring
- **`tests/test_event_types.py`**: `test_incorporation_is_valid_event_type`
- **`tests/test_signal_schemas.py`**: `test_normalize_accepts_incorporation_without_pack`

---

## Configuration

```bash
export INGEST_DELAWARE_SOCRATA_ENABLED=1
export INGEST_DELAWARE_SOCRATA_DATASET_ID=your-dataset-id
```

Optional: `INGEST_DELAWARE_SOCRATA_DATE_COLUMN` (default: `file_date`; validated for SoQL safety)

---

## Verification

- [x] `pytest tests/test_delaware_socrata_adapter.py tests/test_event_types.py tests/test_signal_schemas.py tests/test_ingest_daily.py tests/test_legacy_pack_parity.py -v -W error`
- [x] `ruff check` on modified files — clean
- [x] Snyk code scan: 0 issues on `delaware_socrata_adapter.py`, `event_types.py`, `ingest_daily.py`
- [x] Legacy parity harness passes

## Risk

- **Low**: Additive; fractional CTO flow unchanged
- **Incorporation**: fractional_cto_v1 does NOT adopt; events stored but not scored
- **Delaware**: No confirmed incorporation dataset ID; users browse data.delaware.gov
- **Company resolution**: Incorporation events often lack domain; name-only matching may create duplicates
