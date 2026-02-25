# Signal Models — Canonical Schemas and Pack-Scoping

This document describes the canonical Company Signal data models (events + scores) for SignalForge, aligning with ADR-001 Pack Architecture and Issue #239. It maps v2-spec event types to pack taxonomies and documents pack-scoping rules.

---

## 1. Canonical Schemas

### 1.1 CompanyRead

**Location**: `app/schemas/company.py`

Minimal read schema for companies. Scoring fields (`cto_need_score`) are optional; scores live in snapshots (ReadinessSnapshot, EngagementSnapshot) for pack-scoped resolution.

| Field | Type | Notes |
|-------|------|-------|
| id | int | Primary key |
| company_name | str | |
| domain | str \| None | |
| website_url | str \| None | |
| cto_need_score | int \| None | Denormalized cache for default pack only |
| current_stage | str \| None | |
| created_at, updated_at, last_scan_at | datetime \| None | |

When pack-scoped scores are needed, use `get_company_score(db, company_id, pack_id)` (score_resolver) instead of reading `cto_need_score` directly.

---

### 1.2 CompanySignalEventRead

**Location**: `app/schemas/signals.py`

Canonical event schema for providers and services. Maps from `SignalEvent` ORM. `event_type` is pack-defined (taxonomy `signal_ids`); validated against pack at runtime, not a hardcoded enum.

| Field | Type | Notes |
|-------|------|-------|
| id | int | Primary key |
| company_id | int \| None | FK to companies.id (nullable until resolved) |
| source | str | Adapter identifier (e.g. crunchbase, producthunt) |
| source_event_id | str \| None | Upstream event ID for deduplication |
| event_type | str | Pack-defined; e.g. funding_raised, launch_major |
| event_time | datetime | When the event occurred |
| ingested_at | datetime | When stored |
| title | str \| None | |
| summary | str \| None | |
| url | str \| None | |
| confidence | float \| None | 0..1 |
| pack_id | UUID \| None | Signal pack UUID; None = legacy/unassigned |

**Conversion**: Use `to_company_signal_event_read(signal_event: SignalEvent) -> CompanySignalEventRead` from `app.schemas.signals`.

---

### 1.3 CompanySignalScoreRead

**Location**: `app/schemas/signals.py`

Canonical score schema for composite + dimensions. Aligns with ReadinessSnapshot + EngagementSnapshot.

| Field | Type | Notes |
|-------|------|-------|
| company_id | int | |
| as_of | date | Snapshot date |
| composite | int | 0..100 |
| momentum | int | 0..100 |
| complexity | int | 0..100 |
| pressure | int | 0..100 |
| leadership_gap | int | 0..100 |
| explain | dict \| None | Structured explanation |
| pack_id | UUID \| None | Pack that produced this score |
| computed_at | datetime | |
| esl_score | float \| None | Optional (EngagementSnapshot) |
| esl_decision | str \| None | Optional |
| sensitivity_level | str \| None | Optional |

---

## 2. Event Type Contract

### 2.1 v2-Spec Event Types (v2-spec §3)

The v2-spec defines event types as string constants. SignalForge uses `str` with pack validation at runtime; no hardcoded enum to support pack-specific types.

| v2-Spec Type | fractional_cto_v1 taxonomy signal_id | Dimension |
|--------------|--------------------------------------|-----------|
| funding_raised | funding_raised | M, P |
| job_posted_engineering | job_posted_engineering | M, C |
| job_posted_infra | job_posted_infra | M, C |
| headcount_growth | headcount_growth | M |
| launch_major | launch_major | M |
| api_launched | api_launched | C |
| ai_feature_launched | ai_feature_launched | C |
| enterprise_feature | enterprise_feature | C |
| compliance_mentioned | compliance_mentioned | C |
| enterprise_customer | enterprise_customer | P |
| regulatory_deadline | regulatory_deadline | P |
| founder_urgency_language | founder_urgency_language | P |
| revenue_milestone | revenue_milestone | P |
| cto_role_posted | cto_role_posted | G |
| no_cto_detected | no_cto_detected | G |
| fractional_request | fractional_request | G |
| advisor_request | advisor_request | G |
| cto_hired | cto_hired | G (suppressor) |

**Note**: Issue #239 proposes a TypeScript `EventType` enum (LAUNCH, REPO_ACTIVITY, etc.). In Python, event types are pack-defined via `taxonomy.yaml`; the mapping above documents how v2-spec types map to fractional_cto_v1 `signal_ids`.

### 2.2 Validation

- **With pack**: `normalize_raw_event(raw, source, pack=pack)` validates `event_type_candidate` against `pack.taxonomy.signal_ids`.
- **Without pack**: Falls back to `is_valid_event_type(candidate)` (event_types.py) for legacy paths.

---

## 3. Pack-Scoping Rules

### ADR-002: Pack Version Pinning Per Workspace

Each workspace has an `active_pack_id`. Pack resolution: `get_pack_for_workspace(db, workspace_id)` → workspace's active pack, or default pack when none.

### ADR-009: SignalInstances Are Pack-Scoped

- SignalInstances include `pack_id`, `signal_id`, `entity_id`.
- No cross-pack reuse of SignalInstances.
- Same Observation can produce different Signals under different packs.

### SignalEvent Deduplication

- Unique constraint: `(source, source_event_id)` globally (no pack_id in uniqueness).
- Events are shared upstream; one event stored once.
- `pack_id` on SignalEvent is for attribution, not deduplication.

### AnalysisRecord (when pack_id added)

- `AnalysisRecord.pack_id` attributes analysis to a pack.
- `pack_id IS NULL` treated as default pack until backfill completes.
- **Backfill**: When `pack_id` column is added to AnalysisRecord (Phase 2), existing rows can be backfilled with default pack UUID. Backfill is optional and can be lazy (on next analysis) or via data migration.

---

## 4. Data Flow

```
Ingestion: Adapter → RawEvent → normalize_raw_event (pack validation) → store_signal_event → SignalEvent
           → to_company_signal_event_read() → CompanySignalEventRead (when schema needed)

Scoring:   SignalInstance (pack-scoped) → ReadinessSnapshot + EngagementSnapshot (pack-scoped)
           → CompanySignalScoreRead (when schema needed)

Resolution: get_company_score(db, company_id, pack_id) → ReadinessSnapshot | Company.cto_need_score (default pack)
```

---

## 5. References

- [ADR-001](ADR-001-Introduce-Declarative-Signal-Pack-Architecture.md) — Declarative Signal Pack Architecture
- [ADR-002](ADR-001-Introduce-Declarative-Signal-Pack-Architecture.md) — Pack Version Pinning Per Workspace
- [ADR-009](ADR-001-Introduce-Declarative-Signal-Pack-Architecture.md) — SignalInstances Are Pack-Scoped
- [v2-spec](v2-spec.md) — Event types and data model
- [pipeline](pipeline.md) — Scan vs Ingest/Derive/Score
- [packs/fractional_cto_v1/taxonomy.yaml](../packs/fractional_cto_v1/taxonomy.yaml) — fractional_cto_v1 signal_ids
