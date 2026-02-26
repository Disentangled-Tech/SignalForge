# Pack v2 Contract (Issue #285, M2, M5)

This document defines the Pack v2 schema contract: which files are required vs optional and how validation works. Packs with `schema_version: "2"` in the manifest follow this contract.

## Required files (all schema versions)

- **pack.json** (manifest): `id`, `version`, `name`, `schema_version`
- **scoring.yaml**: Required for all packs. Read by the readiness engine.
- **esl_policy.yaml**: Required for all packs. Used by the ESL engine. Core hard bans (ADR-006) cannot be loosened.

## Optional files for schema_version "2"

- **taxonomy.yaml**: Optional. If absent, the pack is loaded with an empty taxonomy `{}`. Validation of scoring/ESL/derivers uses **core** signal_ids from `app/core_taxonomy/`. If present, it may contain only labels and/or explainability_templates (no `signal_ids` list required).
- **derivers.yaml**: Optional. If absent, the pack is loaded with an empty derivers `{}`. The derive stage uses **core derivers only** (`app/core_derivers/`); pack derivers are not used at runtime. When present, pack derivers are validated at load time against allowed signal_ids (core for v2).

## Validation rules (v2)

- **Allowed signal_ids**: For `schema_version "2"`, the allowed set for scoring base_scores, ESL policy, and (when present) derivers is `get_core_signal_ids()` from `app.core_taxonomy.loader`. Packs cannot introduce new signal IDs.
- **Empty derivers**: For v2, if the pack has no passthrough and no pattern derivers, deriver validation is skipped.
- **ESL**: Core hard bans are still enforced; `validate_esl_policy_against_core_bans` runs for all packs.

## schema_version "1" (backward compatibility)

- **taxonomy.yaml** and **derivers.yaml** are **required**.
- Allowed signal_ids come from the pack taxonomy (non-empty `taxonomy.signal_ids` required).
- fractional_cto_v1 and other existing packs remain on schema_version "1" until explicitly migrated.

## References

- Pack loader: `app/packs/loader.py`
- Pack schema validation: `app/packs/schemas.py` (`_get_allowed_signal_ids`, `_validate_taxonomy`, `_validate_derivers`)
- Core taxonomy: `app/core_taxonomy/`
- Core derivers: `app/core_derivers/`
- CORE_VS_PACK_RESPONSIBILITIES.md (when present): high-level split between core and pack responsibilities.
