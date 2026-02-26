# Ingestion Adapters: GitHub, NewsAPI, Delaware Socrata

Closes #244
Closes #245
Closes #250

## Summary

Adds three ingestion adapters and two core event types:

1. **GitHub** (Issue #244): `repo_activity` from repo/org events; fractional_cto_v1 adopts for Complexity scoring.
2. **NewsAPI** (Issue #245): `funding_raised` from keyword-based news articles.
3. **Delaware Socrata** (Issue #250): `incorporation` from Delaware Open Data; fractional_cto_v1 does NOT adopt.

Core types (`repo_activity`, `incorporation`) are always accepted by normalization regardless of pack taxonomy. Packs that omit them store events but do not score them.

---

## 1. GitHub Adapter (Issue #244)

### Changes

- **`app/ingestion/event_types.py`**: Add `repo_activity` to `SIGNAL_EVENT_TYPES`
- **`app/ingestion/normalize.py`**: Core types always accepted; pack taxonomy types also accepted when pack provided
- **`app/ingestion/adapters/github_adapter.py`** (new): Fetches repo/org events; maps to `RawEvent` with `event_type_candidate='repo_activity'`; fetches org metadata for `website_url` (company resolution)
- **`app/ingestion/adapters/__init__.py`**: Export `GitHubAdapter`
- **`app/services/ingestion/ingest_daily.py`**: Wire when `INGEST_GITHUB_ENABLED=1` and `GITHUB_TOKEN`/`GITHUB_PAT` set
- **`packs/fractional_cto_v1/`**: Add `repo_activity` to taxonomy, derivers, scoring, esl_policy
- **`docs/ingestion-adapters.md`**: GitHub section
- **Tests**: `test_github_adapter.py`, `test_ingest_daily.py`, `test_ingestion_adapter.py`, `test_event_types.py`, `test_signal_schemas.py`, `test_readiness_engine.py`, `test_legacy_pack_parity.py`

### Configuration

```bash
export GITHUB_TOKEN=your-token
export INGEST_GITHUB_ENABLED=1
export INGEST_GITHUB_REPOS=owner/repo1,owner/repo2   # and/or
export INGEST_GITHUB_ORGS=org1,org2
```

---

## 2. NewsAPI Adapter (Issue #245)

### Changes

- **`app/ingestion/adapters/newsapi_adapter.py`** (new): Keyword-based search, company name heuristics, pagination; emits `funding_raised`
- **`app/ingestion/adapters/__init__.py`**: Export `NewsAPIAdapter`
- **`app/services/ingestion/ingest_daily.py`**: Wire when `INGEST_NEWSAPI_ENABLED=1` and `NEWSAPI_API_KEY` set
- **`docs/ingestion-adapters.md`**: NewsAPI section (security note: API key in URL)
- **Tests**: `test_newsapi_adapter.py`, `test_ingest_daily.py`

### Configuration

```bash
export NEWSAPI_API_KEY=your-api-key
export INGEST_NEWSAPI_ENABLED=1
```

Optional: `INGEST_NEWSAPI_KEYWORDS` or `INGEST_NEWSAPI_KEYWORDS_JSON`

---

## 3. Delaware Socrata Adapter (Issue #250)

### Changes

- **`app/ingestion/event_types.py`**: Add `incorporation` to `SIGNAL_EVENT_TYPES`
- **`app/ingestion/adapters/delaware_socrata_adapter.py`** (new): Fetches incorporation filings from Delaware SODA API; maps to `RawEvent` with `event_type_candidate='incorporation'`; validates `INGEST_DELAWARE_SOCRATA_DATE_COLUMN` (alphanumeric/underscore only) to prevent SoQL injection
- **`app/ingestion/adapters/__init__.py`**: Export `DelawareSocrataAdapter`
- **`app/services/ingestion/ingest_daily.py`**: Wire when `INGEST_DELAWARE_SOCRATA_ENABLED=1` and `INGEST_DELAWARE_SOCRATA_DATASET_ID` set
- **`docs/ingestion-adapters.md`**: Delaware Socrata section (dataset ID research, expected schema, company resolution notes)
- **Tests**: `test_delaware_socrata_adapter.py`, `test_ingest_daily.py`, `test_ingestion_adapter.py`, `test_event_types.py`, `test_signal_schemas.py`

### Configuration

```bash
export INGEST_DELAWARE_SOCRATA_ENABLED=1
export INGEST_DELAWARE_SOCRATA_DATASET_ID=your-dataset-id
```

Optional: `INGEST_DELAWARE_SOCRATA_DATE_COLUMN` (default: `file_date`; validated for SoQL safety)

---

## Verification

- [x] `pytest tests/ -v -W error`
- [x] `pytest tests/ -v --cov=app --cov-fail-under=75 -W error`
- [x] `ruff check` on modified files — clean
- [x] Snyk code scan: 0 issues on changed Python files
- [x] Legacy parity harness passes

## Risk

- **Low**: Additive; fractional CTO flow unchanged except for `repo_activity` adoption (higher Complexity)
- **Incorporation**: fractional_cto_v1 does NOT adopt; events stored but not scored
- **Delaware**: No confirmed incorporation dataset ID; users must browse data.delaware.gov
- **Company resolution**: Incorporation events often lack domain; name-only matching may create duplicates
