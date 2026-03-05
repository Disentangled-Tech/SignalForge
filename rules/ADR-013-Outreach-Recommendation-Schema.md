# ADR-013: Outreach Recommendation Schema (Issue #115)

**Status:** Accepted  
**Date:** 2026-03-04

---

## Context

GitHub Issue #115 requested an Outreach Recommendation Schema: add `generation_version`, enforce a pack-aware unique constraint, and optionally a non-PK uuid column. The existing `outreach_recommendations` table had integer PK, `pack_id`/`playbook_id`, and an index on `(company_id, as_of)` but no unique constraint and no `generation_version`.

---

## Decision

- **Schema alignment with #115:** We added nullable `generation_version` (string, 64 chars) and unique constraint `uq_outreach_recommendations_company_as_of_pack` on `(company_id, as_of, pack_id)`.
- **Id remains Integer:** The primary key stays integer (autoincrement). Changing to UUID would break FKs and any code using integer id; a non-PK `uuid` column is deferred for a later milestone if needed for external refs.
- **Unique is (company_id, as_of, pack_id):** Readiness and Engagement snapshots use `(company_id, as_of, pack_id)`. Enforcing only `(company_id, as_of)` would force one recommendation per company per day globally and conflict with multi-pack design; the triple matches the snapshot pattern and keeps ORE output pack-scoped.
- **ORE pipeline:** Writes use upsert by `(company_id, as_of, pack_id)` so re-runs do not insert duplicate rows or violate the constraint.

---

## Consequences

- **Positive:** One recommendation per company per date per pack; version tracking via `generation_version`; backward-compatible (nullable column, additive constraint after dedupe).
- **References:** Issue #115; [docs/signal-models.md](../docs/signal-models.md) §1.4; [Outreach-Recommendation-Engine-ORE-design-spec.md](../docs/Outreach-Recommendation-Engine-ORE-design-spec.md). Issue #123 introduces `draft_generation_number` and `draft_version_history` for versioned regeneration; see signal-models.md §1.4. Tone gating (M5) is prompt-only (additive **TONE_INSTRUCTION**); **sensitivity_level** is never sent to the LLM. Any pack that overrides `ore_outreach_v1` must include **{{TONE_INSTRUCTION}}** in its template—see ORE design spec §Message Template Library.

**Strategy Selector (Issue #117):** The Outreach Strategy Selector is **pack-driven** (playbook supplies pattern_frames, value_assets, ctas, and optional channels and soft_ctas) and uses **core facts** only for TRS dimensions (from ReadinessSnapshot via `get_dominant_trs_dimension`). Selection is **deterministic**—no LLM is used in the selector; the LLM is used only in the draft generator and optional polish step.
