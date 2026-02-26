# Deriver Engine (Issue #173, #192, #285)

The deriver engine populates `signal_instances` from `SignalEvents` (observations) using **core derivers only** (Issue #285). It supports two deriver types: **passthrough** (event_type → signal_id) and **pattern** (regex match on title/summary).

## Core derivers only (Issue #285)

- **Runtime**: The derive stage uses **core derivers** only (`app/core_derivers/`). Pack `derivers.yaml` is **not** used at runtime for the derive stage. See [Core vs Pack Responsibilities](CORE_VS_PACK_RESPONSIBILITIES.md).
- **Pack derivers**: For **schema_version "1"** packs, `derivers.yaml` is still required on disk and validated at pack load time (signal_ids must match pack taxonomy). For **schema_version "2"** packs, `derivers.yaml` is optional; if absent, the pack has empty derivers and derive uses core derivers.
- **Rationale**: Ensures identical `signal_id` output regardless of pack, so scoring/ESL/outreach can vary by pack while the set of derived signals is canonical.
- **Validation**: Pack schema validation still checks pack derivers (when present) against allowed signal_ids (pack taxonomy for v1, core taxonomy for v2). This keeps pack configs consistent; only runtime behavior is core-only.

## Overview

- **Input**: `SignalEvent` rows (pack-scoped, optionally company-scoped)
- **Output**: `SignalInstance` rows (entity-level signals)
- **Rules source**: Core derivers only (`app/core_derivers/derivers.yaml`); see [Core vs Pack Responsibilities](CORE_VS_PACK_RESPONSIBILITIES.md).
- **Idempotency**: Upsert by `(entity_id, signal_id, pack_id)` — re-runs produce the same state
- **Evidence**: Each `SignalInstance` stores `evidence_event_ids` (JSONB list of `SignalEvent.id`)

## Deriver Types

### Passthrough

Maps `event_type` directly to `signal_id`. Used when the event type already corresponds to a taxonomy signal.

```yaml
derivers:
  passthrough:
    - event_type: funding_raised
      signal_id: funding_raised
    - event_type: cto_role_posted
      signal_id: cto_role_posted
```

- **Required fields**: `event_type`, `signal_id`
- **Validation**: Core derivers: `signal_id` must be in core taxonomy (`app/core_taxonomy/taxonomy.yaml`). Pack derivers (when present): validated against allowed signal_ids at pack load time.

### Pattern

Applies a regex to `title` and/or `summary` (or custom `source_fields`) to derive a signal. Used for text-based detection (e.g. compliance keywords).

```yaml
derivers:
  pattern:
    - signal_id: compliance_mentioned
      pattern: "(?i)(security|compliance|soc2|gdpr)"
      source_fields: [title, summary]
      min_confidence: 0.6
```

- **Required fields**: `signal_id`, `pattern` (or `regex`)
- **Optional fields**:
  - `source_fields`: List of SignalEvent attributes to search (default: `[title, summary]`)
  - `min_confidence`: Minimum event confidence to match (default: none)
  - `min_strength`: Reserved for future use
- **Validation**:
  - Core: `signal_id` must be in core taxonomy. Pack (when present): must be in allowed signal_ids.
  - Pattern length ≤ 500 chars (ADR-008)
  - No ReDoS-prone constructs (nested quantifiers)
  - Valid regex syntax

## Schema (derivers.yaml)

**Core** (`app/core_derivers/derivers.yaml`): Used by the deriver engine. Same structure below.

**Pack** (optional for Pack v2): When present, structure is validated at pack load; derive does not use pack derivers. Structure: derivers must be under the top-level `derivers` key. The value is an object with `passthrough` and/or `pattern` lists:

```yaml
derivers:
  passthrough:
    - event_type: <string>
      signal_id: <string>
  pattern:
    - signal_id: <string>
      pattern: <string>   # or regex
      source_fields: [<string>]   # optional; whitelist below
      min_confidence: <float>     # optional
```

**source_fields whitelist**: When `source_fields` is present, it must be a subset of: `title`, `summary`, `url`, `source`. Excludes `raw` (JSONB) and other non-string fields (ADR-008 defense in depth).

Core deriver validation (`app/core_derivers/validator.py`): signal_ids in core taxonomy; regex safety via `app/packs/regex_validator.py`.

Pack schema validation (`app/packs/schemas.py`), when pack has derivers:

- Passthrough entries have `signal_id` in allowed set (core for v2, pack taxonomy for v1)
- Pattern entries have `pattern` or `regex` and `signal_id` in allowed set
- Pattern `source_fields` (when present) must be in whitelist: title, summary, url, source
- Regex safety (`app/packs/regex_validator.py`) validates length and ReDoS guards
- Runtime: per-match regex timeout (100ms) via `regex` package (ADR-008)

## Evidence

Each `SignalInstance` has a nullable `evidence_event_ids` JSONB column:

- **Type**: Array of UUIDs (SignalEvent.id)
- **Purpose**: Traceability from signal back to source events
- **Population**: New runs populate; existing rows may have `NULL` (pre-migration)
- **Aggregation**: Multiple events for same (entity, signal) append event IDs to the list
- **Merge on upsert**: When a SignalInstance already exists (re-run), evidence_event_ids is merged (concatenated and deduplicated) rather than replaced, preserving traceability across derive runs

## Logging

### Per-deriver trigger (INFO)

When a deriver fires for an event:

```
deriver_triggered pack_id=<uuid> signal_id=<string> event_id=<uuid> deriver_type=passthrough|pattern
```

### Completion (INFO)

When the derive stage completes:

```
Deriver completed: pack_id=<uuid> instances_upserted=<int> events_processed=<int> events_skipped=<int>
```

### Debug

At DEBUG level, additional per-event logs include `entity_id`.

## Evaluation Order

1. **Passthrough first**: If `event_type` maps to a signal_id, that signal is added
2. **Pattern second**: Each pattern deriver is evaluated against `source_fields`
3. **Deduplication**: Same signal_id from multiple derivers (e.g. passthrough + pattern) is stored once per (entity, signal)
4. **Confidence filter**: Pattern derivers with `min_confidence` skip events below threshold

## Integration

- **Executor**: `app/pipeline/executor.py` — derive stage requires pack (no derive without pack)
- **Resolver**: `app/services/pack_resolver.py` — `resolve_pack(db, pack_id)` used for job/scoping; deriver engine loads rules from `app/core_derivers/loader.py` (core only)
- **Stage**: `POST /internal/run_derive` — invokes `run_deriver(db, workspace_id, pack_id)`
- **Startup**: Core taxonomy and core derivers are validated at app startup (`app/main.py`); invalid YAML prevents the app from serving

## References

- Core vs Pack: [CORE_VS_PACK_RESPONSIBILITIES.md](CORE_VS_PACK_RESPONSIBILITIES.md) — core derivers only; pack owns scoring/ESL/outreach
- Plan: `.cursor/plans/deriver_engine_pack-driven_implementation_459de0b6.plan.md`; Issue #285: `.cursor/plans/core_taxonomy_deriver_registry_6099ab34.plan.md`
- Pipeline: `docs/pipeline.md`
- Regex safety: ADR-008, `app/packs/regex_validator.py`
- Legacy-vs-Pack Parity Harness: `docs/ISSUE_LEGACY_PACK_PARITY_HARNESS.md`, `tests/test_legacy_pack_parity.py` — verify this doc matches implementation when harness is extended.
- Core taxonomy and derivers: `app/core_taxonomy/`, `app/core_derivers/` (Issue #285); derive uses core only; pack derivers are for schema validation only.
