# Pack v2 Contract

This document defines the **Pack v2** schema contract: required vs optional files, and the rule that **v2 packs provide only analysis weights, ESL rubrics, and prompt bundles** — signals and derivers are core-owned. See [SignalForge Architecture Contract](SignalForge%20Architecture%20Contract) and [CORE_VS_PACK_RESPONSIBILITIES.md](CORE_VS_PACK_RESPONSIBILITIES.md) for the full boundary (Core = Facts, Packs = Interpretation).

---

## 1. Schema versions

- **schema_version "1"** (Pack v1): Legacy contract. Requires `taxonomy.yaml` and `derivers.yaml`; validation uses pack taxonomy `signal_ids`.
- **schema_version "2"** (Pack v2): Aligns with the Architecture Contract. Packs define **weights** (scoring), **ESL rubrics** (esl_policy), and **prompt bundles** (optional). Canonical **signal_ids** and **derivers** are core-owned; validation uses core signal_ids.

---

## 2. Pack v2: Required vs optional files

| File             | v1       | v2                                                                  |
|------------------|----------|---------------------------------------------------------------------|
| pack.json        | Required | Required                                                            |
| scoring.yaml     | Required | Required                                                            |
| esl_policy.yaml  | Required | Required                                                            |
| taxonomy.yaml    | Required | Optional (labels/explainability only; signal_ids come from core)    |
| derivers.yaml    | Required | Optional (derive uses core derivers only)                           |
| playbooks/       | Optional | Optional                                                            |

For v2, if `taxonomy.yaml` or `derivers.yaml` is absent, the loader uses empty dicts and the derive stage uses **core derivers** only. Scoring and ESL policy must reference **core signal_ids** only (validated at load time).

---

## 3. Which packs are v1 vs v2

| Pack               | schema_version | Notes                                                                 |
|--------------------|----------------|-----------------------------------------------------------------------|
| fractional_cto_v1  | "1"            | Production pack; full taxonomy and derivers.                          |
| bookkeeping_v1     | "1"            | Legacy; requires taxonomy and derivers.                               |
| example_v2         | "2"            | Minimal v2 example (no taxonomy/derivers on disk); used by tests.     |

---

## 4. How to add a v2 pack

1. **Create pack directory:** `packs/<pack_id>/`
2. **Add pack.json** with `"schema_version": "2"`, plus `id`, `version`, `name`.
3. **Add required files:** `scoring.yaml`, `esl_policy.yaml`. All `signal_id` references in scoring and ESL must exist in **core taxonomy** (`app/core_taxonomy/taxonomy.yaml`).
4. **Optional:** `taxonomy.yaml` for labels and explainability templates only (no need to list signal_ids; core is source of truth).
5. **Optional:** `derivers.yaml` is not used by the derive stage for v2; include only if you want local validation of custom deriver references against core signal_ids.
6. **Optional:** `playbooks/` for outreach and ORE.

The loader (`app/packs/loader.py`) and schema validator (`app/packs/schemas.py`) enforce: for `schema_version "2"`, allowed signal_ids are taken from `app.core_taxonomy.loader.get_core_signal_ids()`.
