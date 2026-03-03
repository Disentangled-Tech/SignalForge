## M4: Evidence Repository read interface (Issue #276)

### Summary
Implements the read-only Evidence Repository for the Evidence Store (Issue #276). No migrations; no changes to existing ingest/derive/scoring paths.

### Changes
- **`app/evidence/repository.py`** (new): `get_bundle(db, bundle_id)`, `list_bundles_by_run(db, run_id)`, `list_sources_for_bundle(db, bundle_id)`, `list_claims_for_bundle(db, bundle_id)`. Module and function docstrings document workspace/tenant contract (callers must enforce when exposing via API).
- **`app/schemas/evidence.py`**: Add `EvidenceBundleRead`, `EvidenceSourceRead`, `EvidenceClaimRead` for repository responses.
- **`app/evidence/__init__.py`**: Export repository functions.
- **`tests/test_evidence_repository.py`** (new): 9 tests (get by id, list by run, sources for bundle, claims, integration store-then-read).

### Verification
- `pytest tests/test_evidence_repository.py tests/test_evidence_store.py tests/test_evidence_store_schema.py -v -W error` — 27 passed
- Ruff check/format on changed files — clean
- Snyk code scan on `app/evidence/repository.py`, `app/schemas/evidence.py` — 0 issues

### Backward compatibility
- Additive only. No behavior change to fractional CTO, ESL, pipeline, or existing evidence write path.

### Follow-ups (not in this PR)
- M5: Indexing (e.g. index on `run_context->>'run_id'` for `list_bundles_by_run`), quarantine flow.
- M6: Wire Scout to store; when exposing repository via API, enforce workspace in the API layer.
