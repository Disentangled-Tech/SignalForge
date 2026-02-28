## Summary

- **M3 (Issue #276):** Evidence Store write path — `store_evidence_bundle()` with core versioning, source dedupe by `(content_hash, url)`, optional claims with `source_ids`, insert-only immutability.
- **Migration/DB setup fixes:** Core pack sentinel valid UUID, widen `alembic_version.version_num`, idempotent scout_tables migration, safe widen downgrade.

## Changes

### Evidence Store (M3)
- **`app/evidence/store.py`** — `store_evidence_bundle(db, run_id, scout_version, bundles, run_context, raw_model_output, structured_payloads=None, pack_id=None)` → list of `EvidenceBundleRecord`. Injects `core_taxonomy_version` / `core_derivers_version` from loaders; get-or-create `EvidenceSource` by content hash + URL; links via `evidence_bundle_sources`; optional claims from `structured_payloads[i]["claims"]` with `source_refs` → `source_ids`.
- **`app/schemas/evidence.py`** — `EvidenceBundleRecord` (id, created_at, scout_version, core_taxonomy_version, core_derivers_version).
- **`app/evidence/__init__.py`** — exports `store_evidence_bundle`.
- **`app/schemas/__init__.py`** — exports `EvidenceBundleRecord`.
- **`tests/test_evidence_store.py`** — 9 tests (versions, two sources, dedupe, immutability, claims, empty list, run_context, structured_payloads length mismatch, pack_id + raw_model_output).

### Migration / DB fixes
- **`alembic/versions/20260226_add_core_pack_sentinel.py`** — `CORE_PACK_UUID` changed from invalid `c0r3p4ck-...` to valid `c0de0000-0000-4000-8000-000000000001` so migration runs.
- **`alembic/versions/20260226_widen_alembic_version_num.py`** (new) — Widen `alembic_version.version_num` to VARCHAR(64) so long revision IDs (e.g. `20260227_fractional_cto_v2_checksum`) fit. Downgrade only reverts to VARCHAR(32) when current value length ≤ 32 (no truncation).
- **`alembic/versions/20260227_update_fractional_cto_v1_config_checksum_v2.py`** — `down_revision` set to `widen_alembic_ver` so chain is linear after widen.
- **`alembic/versions/20260227_add_scout_runs_and_evidence_bundles.py`** — Idempotent upgrade (skip create if `scout_runs` exists); conditional downgrade using marker table `_alembic_20260227_scout_tables_created` so we only drop when this revision created the tables.

## Verification

- `pytest tests/test_evidence_store.py tests/test_evidence_store_schema.py -v -W error` — 18 passed.
- `alembic upgrade head` on fresh test DB succeeds.
- Ruff clean on modified files.
- Snyk: 0 issues on `app/evidence` and `app/schemas/evidence.py`.
- Branch merged `origin/main` with no conflicts; pushed as `feature/m3-evidence-store`.

## Backward compatibility

- No change to fractional CTO or pack behavior; `get_core_pack_id(db)` resolves by `pack_id='core'` and `version='1'`, not by UUID.
- Evidence store is additive; not yet wired to Scout or any API.

## Checklist

- [x] M3 scope only (write path; no read API, no Scout wire-up).
- [x] Migrations additive or idempotent; downgrades safe where applicable.
- [x] Tests added for store and for pack_id/raw_model_output persistence.
- [x] Branch up to date with main and conflict-free.
