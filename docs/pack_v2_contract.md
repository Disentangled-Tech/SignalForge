# Pack v2 Contract

This document defines the **Pack v2** contract for SignalForge. It aligns with the Architecture Contract: **Core = Facts**, **Packs = Interpretation**.

## Overview

- **Pack v1** (default): Packs provide manifest, taxonomy, derivers, scoring, ESL policy, and playbooks. Validation uses pack-defined `signal_ids` from taxonomy. All of taxonomy.yaml and derivers.yaml are required.
- **Pack v2** (`manifest.schema_version === "2"`): Packs provide **analysis weights**, **ESL rubrics**, and **prompt bundles** only. Signal identifiers and derivers are **core-owned**. Taxonomy and derivers files are optional for v2; when present, validation of scoring/ESL (and optional derivers) uses **core** signal_ids.

## Schema version

- The pack manifest may include `schema_version`. Allowed values: `"1"` (default), `"2"`.
- If `schema_version` is omitted, the pack is treated as **v1**.
- v1 behavior is unchanged: required files and validation rules remain as today.

## Pack-owned (interpretation)

| File                  | v1       | v2                                                                  |
|-----------------------|----------|---------------------------------------------------------------------|
| pack.json             | Required | Required                                                            |
| scoring.yaml          | Required | Optional if `analysis_weights.yaml` present (v2 preferred)           |
| esl_policy.yaml       | Required | Optional if `esl_rubric.yaml` present (v2 preferred)               |
| analysis_weights.yaml | —        | Optional (v2); same semantics as scoring; loader maps to Pack.scoring |
| esl_rubric.yaml       | —        | Optional (v2); same semantics as esl_policy; loader maps to Pack.esl_policy |
| prompt_bundles/       | —        | Optional (v2); system + templates + few_shot; loader sets Pack.prompt_bundles |
| taxonomy.yaml         | Required | Optional (labels/explainability only; signal_ids come from core)    |
| derivers.yaml         | Required | Optional (derive uses core derivers only)                           |
| playbooks/            | Optional | Optional                                                            |

For v2, if `taxonomy.yaml` or `derivers.yaml` is absent, the loader uses empty dicts and the derive stage uses **core derivers** only. For v2, the loader prefers `analysis_weights.yaml` over `scoring.yaml` and `esl_rubric.yaml` over `esl_policy.yaml` when present. Scoring and ESL policy must reference **core signal_ids** only (validated at load time). Core hard bans (e.g. `CORE_BAN_SIGNAL_IDS`) remain enforced and cannot be overridden by packs.

## Core-owned (facts)

Core owns:

- **Signal identifiers**: canonical `signal_ids` and dimensions (see `app/core_taxonomy/`). Derivation uses core derivers (`app/core_derivers/`); for v2 packs, pack derivers are optional (empty dict when absent).
- **Derivers**: event_type → signal_id mappings and pattern derivers are defined in core; packs do not introduce new signals.

## Which packs are v1 vs v2

| Pack               | schema_version | Notes                                                                 |
|--------------------|----------------|-----------------------------------------------------------------------|
| fractional_cto_v1  | "2"            | Production pack (Issue #288 M1); v2 layout: analysis_weights, esl_rubric, prompt_bundles. |
| fractional_cmo_v1   | "2"            | Fractional CMO pack (Issue #288 M2); v2 layout; same core signals, CMO weights/prompts.   |
| fractional_coo_v1   | "2"            | Fractional COO pack (Issue #288 M3); v2 layout; same core signals, COO weights/prompts.   |
| fractional_cfo_v1   | "2"            | Fractional CFO pack (Issue #288 M4); v2 layout; same core signals, CFO weights/prompts.   |
| bookkeeping_v1     | "1"            | Legacy; requires taxonomy and derivers.                               |
| example_v2         | "2"            | Minimal v2 example (no taxonomy/derivers on disk); used by tests.     |

## Required vs optional files

| File            | v1       | v2       |
|-----------------|----------|----------|
| pack.json       | required | required |
| scoring.yaml    | required | required |
| esl_policy.yaml | required | required |
| taxonomy.yaml   | required | optional |
| derivers.yaml   | required | optional |
| playbooks/      | optional | optional |
| prompts/        | n/a      | optional |

For v2, when taxonomy.yaml is absent or omits `signal_ids`, scoring and ESL validation use **core** signal_ids. When derivers.yaml is absent for v2, deriver validation is skipped (derivation still uses core derivers at runtime).

## Validation rules (v2)

- **Scoring**: base_scores, decay, suppressors, recommendation_bands may reference only **core** signal_ids.
- **ESL policy**: svi_event_types, blocked_signals, sensitivity_mapping, prohibited_combinations, downgrade_rules may reference only **core** signal_ids.
- **Derivers** (if present): passthrough and pattern signal_ids must be in **core** taxonomy.
- **Taxonomy** (if present): may contain only labels and explainability_templates; signal_ids list is not required (core is source of truth).

## Backward compatibility

- fractional_cto_v1 has been migrated to schema_version `"2"` (Issue #288 M1); scoring/ESL behavior is unchanged (same weights and rubrics).
- Other packs (e.g. bookkeeping_v1) remain on v1. Migration of a pack to v2 is optional and follows the v2 contract and loader behavior.

## References

- Architecture Contract (SignalForge Architecture Contract doc).
- ADR-001: Declarative Signal Pack Architecture.
- Implementation plan: Pack v2 Contract Implementation (pack_v2_contract_implementation plan).
