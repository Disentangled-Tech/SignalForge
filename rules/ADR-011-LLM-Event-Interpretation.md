# ADR-011: LLM Event Interpretation (Core Event Classification)

**Status:** Accepted  
**Date:** 2026-03-02

⸻

## Context

Issue #281 requires an LLM-based layer that classifies raw content (e.g. diffs or evidence) into validated Core Event candidates with strict schema and taxonomy validation, without introducing new event types or touching signal derivation/scoring. The layer must be reusable by both the Discovery Scout (evidence → events) and the future Diff-Based Monitor (#280) (diff → events).

Dependencies: Core taxonomy (`app/core_taxonomy/`), Extractor validation (`is_valid_core_event_type`), and Evidence Store / verification gate must be in place. Interpretation output is validated against core taxonomy only; pack selection does not alter interpretation result.

⸻

## Decision

- **Interpretation contract:** Input = content (string) + optional evidence list for source_refs. Output = list of CoreEventCandidate (or wrapper with optional snippet per event). Defined in `app/interpretation/schemas.py` (InterpretationInput, InterpretationOutput, InterpretationOutputItem).
- **No new event types:** All interpretation output is validated via existing `is_valid_core_event_type` / CoreEventCandidate. Unknown event types are dropped; no new types are added to the taxonomy.
- **Pack-agnostic:** Interpretation does not take pack_id; prompt and validation use core taxonomy only. "Pack selection does not alter interpretation result" is enforced by design and tests.
- **Reuse:** The same interpretation interface is used by (1) Monitor diff flow (`app/monitor/interpretation.py`: ChangeEvent → CoreEventCandidate list) and (2) future Scout wiring when optional interpretation is enabled (evidence → raw_extraction → extract).
- **Payload key compatibility:** Verification and watchlist seeder accept both `events` and `core_event_candidates` when reading structured_payload, so ExtractionResult and StructuredExtractionPayload shapes both work.

⸻

## Consequences

- **Positive:** Single classification contract for Scout and Diff Monitor; taxonomy-validated output; no cross-tenant or pack leakage in interpretation.
- **Negative:** Two entry points (monitor interpretation vs future Scout interpretation) must stay aligned with the same schema and validation.
- **References:** GitHub issue #281; Architecture Contract §4; docs/discovery_scout.md; docs/event-interpretation.md; docs/monitor.md; app/interpretation/, app/monitor/interpretation.py.
- **TDD / coverage:** Interpretation-related modules are covered by tests (test_interpretation_schemas, test_interpretation_llm, test_monitor_interpretation, test_verification_rules, test_watchlist_seeder). Overall project coverage is maintained ≥75%; interpretation and verification code meet or exceed 85% where exercised.
