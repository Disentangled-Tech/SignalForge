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

Packs define:

- **Analysis weights**: scoring.yaml (base_scores, decay, composite_weights, recommendation_bands, suppressors, pain_signal_weights).
- **ESL rubrics**: esl_policy.yaml (blocked_signals, prohibited_combinations, downgrade_rules, sensitivity_mapping, recommendation_boundaries). Core hard bans (e.g. `CORE_BAN_SIGNAL_IDS`) remain enforced by core and cannot be overridden by packs.
- **Prompt bundles** (v2): optional `packs/{pack_id}/prompts/*.md`; when present, used in preference to `app/prompts/` for that pack.
- **Labels and explainability**: optional in taxonomy (labels, explainability_templates) for human-facing text.

## Core-owned (facts)

Core owns:

- **Signal identifiers**: canonical `signal_ids` and dimensions (see `app/core_taxonomy/`). Derivation uses core derivers first (`app/core_derivers/`); pack derivers are fallback only when core is unavailable.
- **Derivers**: event_type → signal_id mappings and pattern derivers are defined in core; packs do not introduce new signals.

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

- Existing packs (e.g. fractional_cto_v1) remain on schema_version `"1"` with no change in behavior.
- Migration of a pack to v2 is optional and done in a later milestone after the v2 contract and loader behavior are stable and tested.

## References

- Architecture Contract (SignalForge Architecture Contract doc).
- ADR-001: Declarative Signal Pack Architecture.
- Implementation plan: Pack v2 Contract Implementation (pack_v2_contract_implementation plan).
