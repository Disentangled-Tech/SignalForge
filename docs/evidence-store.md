# Evidence Store — Schema and Repository

This document describes the **immutable Evidence Store** for Scout (LLM Discovery) outputs: tables, versioning, and the read-only Evidence Repository. It implements [GitHub issue #276](https://github.com/Disentangled-Tech/SignalForge/issues/276) and aligns with the [SignalForge Architecture Contract](SignalForge%20Architecture%20Contract) (Evidence = Core; pack-agnostic). The store is a **separate lineage** from the ingest/derive pipeline: it does not write to `signal_events`, `signal_instances`, or companies.

---

## 1. Purpose

- **Persist Scout outputs** — When a Scout run produces `EvidenceBundle` results, the store writes them to `evidence_bundles`, `evidence_sources`, and (optionally) `evidence_claims`.
- **Version against core** — Every bundle records `core_taxonomy_version` and `core_derivers_version` at write time for audit and reproducibility.
- **Immutability** — Bundles are insert-only; no `updated_at` or UPDATE on `evidence_bundles`.
- **Quarantine** — Invalid or rejected payloads are written to `evidence_quarantine` with a reason; no FK to bundles.

The Evidence Store is **not** used by the ingest → derive → score pipeline. Evidence in that pipeline is tracked via `SignalInstance.evidence_event_ids` (references to `SignalEvent` rows). See [signal-models.md](signal-models.md) and [deriver-engine.md](deriver-engine.md) for that flow.

---

## 2. Tables

### 2.1 evidence_bundles

One row per evidence bundle from a Scout run. Append-only; no `updated_at`.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| scout_version | str (128) | Scout/model version at write time |
| core_taxonomy_version | str (64) | From `get_core_taxonomy_version()` |
| core_derivers_version | str (64) | From `get_core_derivers_version()` |
| pack_id | UUID (nullable) | FK to signal_packs.id; **analytics-only**, no pack behavior in store |
| run_context | JSONB (nullable) | e.g. `{"run_id": "...", "workspace_id": "..."}`; used for listing by run |
| raw_model_output | JSONB (nullable) | Raw LLM output for audit |
| structured_payload | JSONB (nullable) | Optional structured extraction (e.g. claims) |
| created_at | timestamptz | Insert time |

**Index:** `(core_taxonomy_version, core_derivers_version)` for version-based queries.

**Location:** `app/models/evidence_bundle.py`

### 2.2 evidence_sources

Deduplicated sources (URL + content hash of snippet). Shared across bundles via the join table.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| url | str (2048) | Source URL |
| retrieved_at | timestamptz (nullable) | When the page/snippet was retrieved |
| snippet | text (nullable) | Quoted snippet |
| content_hash | str (64) | SHA-256 hex of snippet; used for dedupe |
| source_type | str (64) (nullable) | e.g. "web_page" |

**Unique constraint:** `(content_hash, url)` — same content+URL is stored once.

**Location:** `app/models/evidence_source.py`

### 2.3 evidence_bundle_sources

Join table: many-to-many between `evidence_bundles` and `evidence_sources`. Links each bundle to its evidence items (sources).

| Column | Type | Notes |
|--------|------|-------|
| bundle_id | UUID | FK to evidence_bundles.id (CASCADE) |
| source_id | UUID | FK to evidence_sources.id |

**Location:** `app/models/evidence_bundle_source.py`

### 2.4 evidence_claims

Structured claims (entity_type, field, value) scoped to a bundle; each claim can reference source IDs.

| Column | Type | Notes |
|--------|------|-------|
| id | serial | Primary key |
| bundle_id | UUID | FK to evidence_bundles.id (CASCADE) |
| entity_type | str (64) | e.g. "company" |
| field | str (255) | e.g. "name" |
| value | text (nullable) | Claim value |
| source_ids | JSONB (nullable) | List of evidence_sources.id (UUIDs) backing this claim |
| confidence | float (nullable) | 0..1 |

**Location:** `app/models/evidence_claim.py`

### 2.5 evidence_quarantine

Items that failed validation (e.g. schema mismatch, length). No FK to bundles; payload can contain run_id for correlation.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| payload | JSONB | Rejected payload (e.g. full request body) |
| reason | text (nullable) | Human-readable reason |
| created_at | timestamptz | Insert time |

**Location:** `app/models/evidence_quarantine.py`

---

## 3. Versioning

- **Core taxonomy version** — `get_core_taxonomy_version()` in `app/core_taxonomy/loader.py` (from taxonomy YAML `version` or content hash).
- **Core derivers version** — `get_core_derivers_version()` in `app/core_derivers/loader.py` (from derivers YAML `version` or content hash).

Every `store_evidence_bundle()` call injects these versions into each new `evidence_bundles` row. Downstream (e.g. extraction, verification) can interpret bundles in the context of the taxonomy/derivers that were active at write time.

---

## 4. pack_id

`pack_id` on `evidence_bundles` is **analytics-only**. The Evidence Store does not:

- Filter or scope reads by pack
- Apply pack-specific derivation or scoring
- Change behavior based on pack

Packs own interpretation (scoring, ESL, outreach); the Evidence Store remains pack-agnostic per the Architecture Contract. If a Scout run is associated with a pack (e.g. for query emphasis), that pack can be stored for analytics; it does not affect store or repository logic.

---

## 5. Evidence Repository (read interface)

The **Evidence Repository** is a read-only layer used by APIs or services that need to fetch persisted bundles, sources, and claims. It does **not** enforce workspace or tenant boundaries; the **caller** (e.g. internal API that resolves `run_id` from a workspace-scoped Scout run) must enforce access control.

**Location:** `app/evidence/repository.py`

| Function | Description |
|----------|-------------|
| `get_bundle(db, bundle_id)` | Return one bundle by id, or None. Returns `EvidenceBundleRead` (Pydantic). |
| `list_bundles_by_run(db, run_id)` | Return all bundles whose `run_context.run_id` equals `run_id`. |
| `list_sources_for_bundle(db, bundle_id)` | Return all evidence sources linked to the bundle (via join table). |
| `list_claims_for_bundle(db, bundle_id)` | Return all claims for the bundle. |

Read schemas: `EvidenceBundleRead`, `EvidenceSourceRead`, `EvidenceClaimRead` in `app/schemas/evidence.py`.

---

## 6. Evidence Store (write path)

**Location:** `app/evidence/store.py`

- **`store_evidence_bundle(db, run_id, scout_version, bundles, run_context, raw_model_output, ...)`** — Inserts one `evidence_bundles` row per Scout `EvidenceBundle`; for each evidence item, get-or-create `evidence_sources` by `(content_hash, url)` and link via `evidence_bundle_sources`; optionally insert `evidence_claims` from structured payload. Invalid inputs (e.g. length mismatch) are written to `evidence_quarantine` instead of bundles. Insert-only; no UPDATE on bundles.

Scout integration: `app/services/scout/discovery_scout_service.py` calls `store_evidence_bundle()` after persisting `ScoutRun` and `ScoutEvidenceBundle`. Optional internal endpoint: `POST /internal/evidence/store` accepts a Scout-run-shaped body for testing or non-Scout callers.

---

## 7. References

- [Discovery Scout](discovery_scout.md) — Scout flow and Evidence Bundle output schema
- [SignalForge Architecture Contract](SignalForge%20Architecture%20Contract) — §2.1 Evidence (immutable, versioned, pack-agnostic)
- [signal-models.md](signal-models.md) — Company Signal models (events, scores); separate from Evidence Store
- [pipeline.md](pipeline.md) — Scan vs ingest/derive/score; Scout as separate flow
