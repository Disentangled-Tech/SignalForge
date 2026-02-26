# Core Signal Taxonomy & Core Deriver Registry (Issue #285)

## Summary

Introduces pack-independent **Core Signal Taxonomy** and **Core Deriver Registry**. The derive stage uses core derivers only; normalization validates against core taxonomy when pack is absent or has no taxonomy. Packs retain scoring, ESL, and outreach; v2 packs may omit taxonomy/derivers and rely on core.

Related to #285 (this PR references the issue but does not close it).

### Incorporation (Issue #250)

- **Core taxonomy**: `incorporation` remains in `app/core_taxonomy/taxonomy.yaml` with a comment that it is accepted at ingest for company resolution and intentionally omitted from core derivers passthrough.
- **Core derivers**: `incorporation` removed from `app/core_derivers/derivers.yaml` passthrough list. Derive does not produce SignalInstances for incorporation; NOTE in derivers.yaml updated to match.
- **Ingest**: Incorporation events still accepted at normalization (core taxonomy + legacy `SIGNAL_EVENT_TYPES`).

### Example v2 pack

- **`packs/example_v2/`** added: minimal Pack v2 (schema_version `"2"`) with no `taxonomy.yaml` or `derivers.yaml` on disk. Used by tests to verify v2 optional files and derive using core derivers only.

---

## Changes

| Area | Change |
|------|--------|
| **Core taxonomy** | `app/core_taxonomy/`: canonical `signal_ids` and dimensions; `is_valid_signal_id()`, `get_core_signal_ids()`; startup validation in `main.py`. |
| **Core derivers** | `app/core_derivers/`: canonical event_type → signal_id passthrough (+ optional pattern); validator enforces core taxonomy + regex safety (ADR-008). |
| **Normalization (M4)** | `normalize.py` uses core taxonomy when pack is `None` or has no taxonomy; legacy `SIGNAL_EVENT_TYPES` kept for backward compat (e.g. incorporation). `is_valid_event_type` delegates to core. |
| **Deriver engine (M6)** | Derive uses **core derivers only**; pack deriver fallback removed. Event filtering by `pack_id` unchanged. |
| **Pack loader (M5)** | For `schema_version "2"`, `taxonomy.yaml` and `derivers.yaml` are optional; empty dicts when absent. |
| **Pack schema** | v2 validates scoring/ESL/derivers against core signal_ids; v2 may have empty derivers (skip validation). |
| **Daily aggregation** | `DailyAggregationResult` TypedDict; early return when no pack; `ranked_companies` uses `outreach_score_threshold=0` (monitoring population); API docstring for `ranked_count`. |
| **Docs** | `docs/CORE_VS_PACK_RESPONSIBILITIES.md` (new); `docs/deriver-engine.md` and `docs/signal-models.md` updated; incorporation note in `core_derivers/derivers.yaml`. |
| **Tests** | Core taxonomy/derivers tests; normalizer core/legacy tests; parity test for derived signal_ids vs core passthrough; v2 load_pack and deriver-with-v2-pack tests; core load failure → job failed (no pack fallback). |
| **Example pack** | `packs/example_v2/`: minimal v2 pack (no taxonomy/derivers on disk) for loader and deriver tests. |

---

## Verification

- `pytest tests/ -v -W error` (relevant subsets / full suite)
- `ruff check app/ tests/` — clean
- Snyk — no issues on changed code
- Coverage ≥75% overall; modified modules ≥85% where required

---

## Backward compatibility & risk

- **fractional_cto_v1** (schema_version `"1"`): Unchanged; still requires taxonomy and derivers. Derive output matches prior behavior (core derivers extracted from that pack; passthrough-only).
- **Pack scoping**: `pack_id` filtering in deriver and elsewhere unchanged; no cross-tenant impact.
- **ESL**: Core hard bans still enforced; pack cannot loosen (ADR-006).
- **Deployment**: App requires `app/core_taxonomy/` and `app/core_derivers/` (and their YAML); missing/invalid core YAML causes startup failure (fail-fast).

---

## Checklist

- [x] All tests pass (with `-W error`)
- [x] Linter (Ruff) clean
- [x] Snyk clean on changed code
- [x] No new migrations; no schema changes
- [x] Docs updated (CORE_VS_PACK_RESPONSIBILITIES, deriver-engine, signal-models)
