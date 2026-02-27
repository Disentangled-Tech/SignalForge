# Core taxonomy & deriver registry (Issue #285); Pack v2 optional taxonomy/derivers

Related to #285

## Summary

Introduces pack-independent **Core Signal Taxonomy** and **Core Deriver Registry**. Derive uses core derivers only; normalization can validate against core taxonomy when pack is absent or has no taxonomy. Pack v2 (`schema_version "2"`) may omit `taxonomy.yaml` and `derivers.yaml` and rely on core. Adds `packs/example_v2/` and documents the Pack v2 contract.

## Changes

| Area | Change |
|------|--------|
| **Core taxonomy** | `app/core_taxonomy/`: canonical `signal_ids` and dimensions; `is_valid_signal_id()`, `get_core_signal_ids()`; loader + validator. |
| **Core derivers** | `app/core_derivers/`: canonical event_type → signal_id passthrough; loader + validator; regex safety (ADR-008). |
| **Pack v2 contract** | `docs/pack_v2_contract.md`: required vs optional files; core-owned vs pack-owned; v2 validation rules. |
| **Pack loader (M5)** | For `schema_version "2"`, `taxonomy.yaml` and `derivers.yaml` optional; empty dicts when absent. |
| **Pack schema** | v2: validate scoring/ESL/derivers against core signal_ids; empty derivers skip validation. |
| **Deriver engine (M6)** | Derive uses **core derivers only**; pack deriver fallback removed. Core load failure → job failed. |
| **Example pack** | `packs/example_v2/`: minimal v2 pack (no taxonomy/derivers on disk). |
| **Tests** | Pack schema (schema_version, v2 optional files); deriver (core-only behavior, v2 pack); daily aggregation. |

## Verification

- [x] `pytest tests/ -v -W error` (relevant subsets / full suite)
- [x] `ruff check app/ tests/` — clean
- [x] No new migrations; no schema changes

## Backward compatibility

- **fractional_cto_v1** (schema_version `"1"`): Unchanged; taxonomy and derivers still required. Derive output matches prior behavior (core derivers align with prior pack passthrough).
- **Pack scoping**: `pack_id` filtering unchanged; no cross-tenant impact.

## Checklist

- [ ] All tests pass (with `-W error`)
- [ ] Linter (Ruff) clean
- [ ] Docs updated (pack_v2_contract, CORE_VS_PACK if present)
