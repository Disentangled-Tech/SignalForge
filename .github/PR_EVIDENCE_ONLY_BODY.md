# Evidence-Only Pack Mode + Company Resolver Normalization

Related to #275 (LLM Discovery Scout — Evidence-Only Mode)

Implements the pack-level **evidence-only** mode and wiring that enables discovery packs to surface evidence without generating outreach drafts. This is foundational for the full LLM Discovery Scout (#275).

## Summary

- **Evidence-only packs**: Packs can set `evidence_only: true` in manifest; briefing and ORE skip draft generation and show "Evidence only — no draft".
- **Discovery pack**: Adds `llm_discovery_scout_v0` pack and migration; `POST /internal/run_scan?evidence_only=true` uses it when installed.
- **Schema validation**: `evidence_only` in manifest must be boolean when present.

## Changes

### Pack interfaces & evidence-only
- `PackOutreachInterface` and `adapt_pack_for_outreach` read `evidence_only` from manifest
- Briefing, ORE pipeline, and company detail skip outreach draft when pack is evidence-only
- `get_discovery_pack_id()` resolves `llm_discovery_scout_v0` when installed
- `run_scan_all(evidence_only=True)` uses discovery pack; `POST /internal/run_scan?evidence_only=true` forwards param
- Pack schema: `evidence_only` must be bool when present

### UI
- Briefing template: "Evidence only — no draft" when pack is evidence-only
- Company detail: same message when pack is evidence-only

### Packs
- `fractional_cto_v1`: `evidence_only: false`
- `llm_discovery_scout_v0`: new pack with `evidence_only: true`

### Tests
- Pack interfaces, schema validation, pack resolver, scan orchestrator, briefing, internal API, company detail
