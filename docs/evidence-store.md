# Evidence Store — Schema and Repository

This document describes the **immutable Evidence Store** for Scout (LLM Discovery) outputs: tables, versioning, and the read-only Evidence Repository. It implements [GitHub issue #276](https://github.com/Disentangled-Tech/SignalForge/issues/276) and aligns with the [SignalForge Architecture Contract](SignalForge%20Architecture%20Contract) (Evidence = Core; pack-agnostic). The store is a **separate lineage** from the ingest/derive pipeline: it does not write to `signal_events`, `signal_instances`, or companies. Monitoring and diff detection (e.g. the Diff-Based Monitor, see [monitor.md](monitor.md)) are also Core-owned and pack-agnostic; they do not use the Evidence Store but share the same Core boundary.

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
| structured_payload | JSONB (nullable) | Optional structured extraction (e.g. claims, or Extractor output—see below) |
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

When quarantine is triggered by the **Verification Gate** (Issue #278), `payload` must include **`reason_codes`**: a list of strings (e.g. `EVENT_TYPE_UNKNOWN`, `EVENT_MISSING_TIMESTAMPED_CITATION`). The `reason` column is set to a human-readable summary (e.g. `"; ".join(reason_codes)`). A future migration may add an optional `reason_codes` column for filtering; until then, consumers read `payload.get("reason_codes")`.

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

The **Evidence Repository** is a read-only layer. For **workspace-scoped access**, use the functions that enforce tenant boundaries: **`get_bundle_for_workspace(db, bundle_id, workspace_id)`** and **`list_bundles_by_run_for_workspace(db, run_id, workspace_id)`**. The raw `get_bundle(db, bundle_id)` and `list_bundles_by_run(db, run_id)` do not filter by workspace; any API that exposes bundle-by-id or list-by-run must use the workspace-scoped variants (or equivalent) to avoid cross-tenant data access.

**Location:** `app/evidence/repository.py`

| Function | Description |
|----------|-------------|
| `get_bundle(db, bundle_id)` | Return one bundle by id, or None. **Does not enforce workspace.** Caller must scope. |
| `get_bundle_for_workspace(db, bundle_id, workspace_id)` | Return bundle only if its run belongs to `workspace_id`; else None. Use for any bundle-by-id API. |
| `list_bundles_by_run(db, run_id)` | Return all bundles whose `run_context.run_id` equals `run_id`. Caller must scope. |
| `list_bundles_by_run_for_workspace(db, run_id, workspace_id)` | Return bundles for `run_id` only if the run belongs to `workspace_id`; else []. |
| `list_sources_for_bundle(db, bundle_id)` | Return all evidence sources linked to the bundle (via join table). |
| `list_claims_for_bundle(db, bundle_id)` | Return all claims for the bundle. |

Read schemas: `EvidenceBundleRead`, `EvidenceSourceRead`, `EvidenceClaimRead` in `app/schemas/evidence.py`.

---

## 6. Evidence Store (write path)

**Location:** `app/evidence/store.py`

- **`store_evidence_bundle(db, run_id, scout_version, bundles, run_context, raw_model_output, ...)`** — Inserts one `evidence_bundles` row per Scout `EvidenceBundle`; for each evidence item, get-or-create `evidence_sources` by `(content_hash, url)` and link via `evidence_bundle_sources`; optionally insert `evidence_claims` from structured payload. Invalid inputs (e.g. length mismatch) are written to `evidence_quarantine` instead of bundles. Insert-only; no UPDATE on bundles.

**Scout integration:** `app/services/scout/discovery_scout_service.py` calls `store_evidence_bundle()` after persisting `ScoutRun` and `ScoutEvidenceBundle`. When the **Verification Gate** is enabled (config `SCOUT_VERIFICATION_GATE_ENABLED`), Scout runs `verify_bundles()` first; bundles that fail verification are quarantined (with `reason_codes` in payload) and only passing bundles are stored. See [Discovery Scout](discovery_scout.md#verification-optional-m3-issue-278). Optional internal endpoint: `POST /internal/evidence/store` accepts a Scout-run-shaped body for testing or non-Scout callers.

**When populated by the Extractor:** When the optional [Evidence Extractor](discovery_scout.md#optional-extractor-m4-issue-277) is enabled (config `SCOUT_RUN_EXTRACTOR` or `run_extractor=True`), each bundle's `structured_payload` is populated with **ExtractionResult** shape: `company` (normalized company object), `person` (optional), `core_event_candidates` (list of core-event candidates, taxonomy-validated), and `version` (payload version string). The Extractor does not derive signals; it emits only core-event types (validated against core taxonomy) and all outputs are source-backed (fields/events mapped to source_refs). See `app/extractor/schemas.py`.

### 6.1 Structured payload contract (recommended producer schema)

The `structured_payload` column accepts any JSON-serializable dict. For producers (e.g. extractors) that want validated, store-compatible output, the **recommended contract** is **`StructuredExtractionPayload`** from `app/schemas/core_events.py`. It defines:

- **version** — Payload version (e.g. `"1.0"`) for evolution.
- **events** — List of `CoreEventCandidate` (core taxonomy event types only).
- **company** / **persons** — Normalized entity shapes.
- **claims** — List of `ExtractionClaim` (entity_type, field, value, source_refs, confidence). When present, the store inserts `evidence_claims` rows and resolves `source_refs` (0-based indices into the bundle's evidence) to `evidence_sources.id`.

Serializing with `StructuredExtractionPayload.model_dump(mode="json")` yields a dict that `store_evidence_bundle` accepts and that matches the store's expectations for `payload["claims"]` (see `app/evidence/store.py`). Out-of-range `source_refs` are ignored; only indices `0 <= ref < len(evidence)` are resolved to source IDs.

### 6.2 Verification Gate (Issue #278)

Before evidence enters the store, bundles can be validated by a **Verification Gate** that enforces pack-agnostic fact and event rules. The gate runs only when explicitly enabled (Scout config or internal store request). It is owned by Core per the [SignalForge Architecture Contract](SignalForge%20Architecture%20Contract) (§2 Core Responsibilities: Verification & grounding rules).

#### When it runs

- **Scout path:** When the verification gate is enabled (e.g. `SCOUT_VERIFICATION_GATE_ENABLED`), the Scout service runs `verify_bundles()` after validation and optional extraction. Bundles that fail are quarantined (with structured reason codes); only passing bundles are passed to `store_evidence_bundle`. When the gate is disabled, all validated bundles go to the store as before.
- **Internal store path:** `POST /internal/evidence/store` can request verification via a body flag; when set, the same verify → quarantine failures → store only passing flow applies.

#### Rules applied

- **Event rules:** Event type must be in the core taxonomy; each event must have at least one timestamped citation (source_ref to evidence with `timestamp_seen`); required fields (event_type, confidence) must be present. See `app/verification/rules.py` and `VerificationReasonCode` in `app/verification/schemas.py` for reason codes (e.g. `EVENT_TYPE_UNKNOWN`, `EVENT_MISSING_TIMESTAMPED_CITATION`, `EVENT_MISSING_REQUIRED_FIELDS`).
- **Fact rules:** Website domain must match at least one cited evidence URL; founder facts require ≥1 primary source; hiring-related events require a valid jobs page or ATS source. Reason codes include `FACT_DOMAIN_MISMATCH`, `FACT_FOUNDER_MISSING_PRIMARY_SOURCE`, `FACT_HIRING_MISSING_JOBS_OR_ATS`.

#### Quarantine payload shape (verification-triggered)

When the gate quarantines a bundle, the same `evidence_quarantine` row is used: `reason` is a human-readable summary (e.g. concatenation of reason codes), and **`payload` must include `reason_codes`** (list of strings) for structured filtering and review. Existing consumers that only read `reason` remain supported; the Quarantine review API exposes `reason_codes` from the payload when present (see §7).

**Location:** `app/verification/` (service, rules, schemas); orchestration in Scout and internal API.

---

## 7. Quarantine review API (M4, Issue #278)

**Endpoints:** `GET /internal/evidence/quarantine` (list) and `GET /internal/evidence/quarantine/{id}` (detail). Both require the **X-Internal-Token** header; they are internal-only and intended for cron/scripts, not end-user or tenant-facing APIs.

**Cross-tenant semantics:** The `evidence_quarantine` table has **no workspace column**. List and get return rows from the entire table with no workspace or tenant filter. Product may add workspace scoping later (e.g. store `workspace_id` in payload or add a column) if filtering by tenant is required.

**List query params:** `limit` (1–500), `offset`, optional `reason_substring` (case-insensitive filter on `reason`), optional `since` (ISO 8601; only entries with `created_at >= since`). Response shape: `{ "entries": [...], "count": N }`. When the verification gate quarantines a bundle, `payload` includes `reason_codes` (list of strings); the read schema exposes them as `reason_codes` on each entry.

**Payload sensitivity:** Quarantine `payload` can contain run context, bundle content, company names, and quoted snippets. It is intended only for internal/cron use with the internal token; do not expose the quarantine API to untrusted or tenant-facing callers without adding filtering and access control.

---

## 8. References

- [Discovery Scout](discovery_scout.md) — Scout flow and Evidence Bundle output schema
- [SignalForge Architecture Contract](SignalForge%20Architecture%20Contract) — §2.1 Evidence (immutable, versioned, pack-agnostic)
- [signal-models.md](signal-models.md) — Company Signal models (events, scores); separate from Evidence Store
- [pipeline.md](pipeline.md) — Scan vs ingest/derive/score; Scout as separate flow
