# Core vs Pack Responsibilities (Issue #285)

This document describes the split between **core** (pack-independent) and **pack** (pack-specific) configuration after the Core Taxonomy and Core Deriver Registry refactor. Derive produces identical `SignalInstance` outputs regardless of pack; packs control scoring, ESL, and outreach.

---

## 1. Core (Pack-Independent)

Core configuration lives in `app/core_taxonomy/` and `app/core_derivers/`. It is the single source of truth for:

- **Canonical signal_ids** — The set of valid signal identifiers used in derive and in cross-pack validation. Defined in `app/core_taxonomy/taxonomy.yaml` (signal_ids list and dimensions).
- **Event type → signal_id mapping (passthrough)** — Canonical `event_type` → `signal_id` passthrough rules. Defined in `app/core_derivers/derivers.yaml` under `derivers.passthrough`. All passthrough `signal_id` values must exist in core taxonomy.
- **Pattern → signal_id (optional)** — Core may define pattern derivers (regex on title/summary, etc.) in `derivers.pattern`. When present, they use the same schema and regex safety rules as pack pattern derivers.
- **Regex safety** — Pattern derivers (core or pack) are validated for length and ReDoS-safe constructs (ADR-008). Core derivers use `app/packs/regex_validator.py`; core validator ensures pattern entries reference core taxonomy signal_ids.

**Used by:**

- **Ingestion**: Event type validation can use core taxonomy when pack is absent or when pack has no taxonomy (e.g. Pack v2 with optional taxonomy).
- **Derive**: The deriver engine uses **core derivers only**. It does not read pack `derivers.yaml` for passthrough or pattern rules. Derive runs without a pack and writes SignalInstances with core pack_id (Issue #287).
- **Pack schema**: For Pack v2, scoring/ESL/derivers validation uses core signal_ids when pack taxonomy is minimal or empty.

**References:** `app/core_taxonomy/loader.py`, `app/core_derivers/loader.py`, `app/pipeline/deriver_engine.py`, `app/ingestion/normalize.py`, `app/packs/schemas.py`.

---

## 2. Pack (Pack-Specific)

Pack configuration lives under `packs/<pack_id>/`. Packs own:

- **Scoring** — Weights, decay, caps, base_scores, suppressors. Defined in `scoring.yaml` (or for Pack v2, `analysis_weights.yaml`; loader maps to same Pack.scoring). Read by the readiness engine; determines composite and dimension scores from SignalInstances.
- **ESL policy** — SVI/SPI/CSI, boundaries, hard bans. Defined in `esl_policy.yaml` (or for Pack v2, `esl_rubric.yaml`; loader maps to same Pack.esl_policy). Used by the ESL engine for engagement scoring and gating.
- **Outreach** — Playbooks, offer type, outreach logic. Defined in `playbooks/` and pack manifest. Used by ORE and briefing.
- **Labels and explainability templates** — Human-readable labels and explanation templates for signals. May live in pack `taxonomy.yaml` (optional in Pack v2). Used for UI and explainability.
- **Optional taxonomy (Pack v2)** — Packs with `schema_version: "2"` may omit `taxonomy.yaml` or use it only for labels/explainability; core taxonomy is used for signal_id validation.
- **Optional derivers (Pack v2)** — Packs with `schema_version: "2"` may omit `derivers.yaml`; derive uses core derivers only.

**Not used by derive:** The deriver engine does not use pack `derivers.yaml` for passthrough or pattern rules (Issue #285, Milestone 6). Pack derivers are only validated at pack load time (when present) against allowed signal_ids (core for v2).

**Default pack:** The default pack is **fractional_cto_v1** by convention (see `app/services/pack_resolver.py`). v2 packs use the same resolution path: `get_default_pack_id` / `get_pack_for_workspace` return the pack UUID from `signal_packs`; `resolve_pack` loads the pack from disk via `load_pack(pack_id, version)` regardless of schema_version.

**References:** `app/packs/loader.py`, `app/services/readiness/readiness_engine.py`, `app/services/esl/esl_engine.py`, `app/services/ore/ore_pipeline.py`, `app/packs/schemas.py`, `app/services/pack_resolver.py`.

---

## 3. Derive: Core Only (Issue #287)

- **Runs without a pack**: Derive does not require a workspace pack; it uses core derivers only and writes to the **core** pack_id (core pack sentinel in `signal_packs`).
- **Input**: SignalEvents (all events with `company_id`; no filter on `SignalEvent.pack_id` when writing to core).
- **Rules**: Passthrough and pattern rules come from **core derivers only** (`app/core_derivers/`). No fallback to pack derivers.
- **Output**: SignalInstances keyed by `(entity_id, signal_id, pack_id)` with `pack_id` = core pack UUID. Same events produce the same `signal_id` values; only one canonical set of instances (core) is written.
- **Startup**: Core taxonomy and core derivers are validated at application startup; invalid or missing core YAML prevents the app from serving (fail-fast).

See `docs/deriver-engine.md` for deriver types, schema, and integration.

---

## 4. Score: Core input, pack interpretation (Issue #287)

- **Input**: Core SignalInstances (via evidence events). The snapshot writer loads event-like data from core instances for each company; pack is not used to select which signals exist.
- **Pack**: Weights and ESL rubric only. The workspace pack supplies `scoring.yaml` and `esl_policy.yaml`; it does not define or filter the signal set.
- **Output**: ReadinessSnapshot and EngagementSnapshot remain pack-scoped (keyed by workspace `pack_id`); only the **source** of the event list for scoring and ESL signal set is core.

---

## 5. Core config: loading and caching (ops)

Core taxonomy (`app/core_taxonomy/taxonomy.yaml`) and core derivers (`app/core_derivers/derivers.yaml`) are **loaded at application startup** and **cached in process** (`load_core_taxonomy`, `load_core_derivers`, and their accessors use `@lru_cache`). Edits to these YAML files do not take effect until the application is restarted. For config changes in production, plan for a restart or rolling deploy so all processes pick up the new core config.

---

## 6. Summary Table

| Concern                    | Owner   | Location / usage                                      |
| -------------------------- | ------- | ----------------------------------------------------- |
| Canonical signal_ids       | Core    | `app/core_taxonomy/taxonomy.yaml`                     |
| Dimensions (M, C, P, G)    | Core    | `app/core_taxonomy/taxonomy.yaml`                     |
| Passthrough (event→signal) | Core    | `app/core_derivers/derivers.yaml`; used by derive    |
| Pattern derivers           | Core    | `app/core_derivers/derivers.yaml` (optional); derive |
| Regex safety               | Shared  | `app/packs/regex_validator.py`; core + pack          |
| Scoring weights/decay/caps | Pack    | `packs/<pack_id>/scoring.yaml` (v2: `analysis_weights.yaml`)   |
| ESL policy                 | Pack    | `packs/<pack_id>/esl_policy.yaml` (v2: `esl_rubric.yaml`)     |
| Outreach playbooks         | Pack    | `packs/<pack_id>/playbooks/`, manifest                |
| Labels / explainability    | Pack    | `packs/<pack_id>/taxonomy.yaml` (optional in v2)      |

---

## 7. References

- Implementation plan: `.cursor/plans/core_taxonomy_deriver_registry_6099ab34.plan.md`
- Deriver engine: `docs/deriver-engine.md`
- Signal models and pack-scoping: `docs/signal-models.md`
- ADR-008 (regex safety): `app/packs/regex_validator.py`
- Legacy parity: `docs/ISSUE_LEGACY_PACK_PARITY_HARNESS.md`, `tests/test_legacy_pack_parity.py`
