# ADR-010: Extractor Service (Structured Entity/Event Parsing)

**Status:** Accepted  
**Date:** 2026-03-02

⸻

## Context

Issue #277 requires an Extractor that converts Evidence Bundles into normalized entity fields (Company, Person) and Core Event candidates only—without signal derivation. The codebase already had a module named `app/services/extractor.py` used for HTML text extraction (BeautifulSoup). A separate service was needed for structured entity/event parsing from Evidence Bundles, with no change to existing Scout or Evidence Store behavior until opt-in integration.

Dependencies: Evidence Store (#276) and core taxonomy/derivers (#285) must be in place. The Extractor must not write to `signal_events` or create `SignalInstance` rows; that is a separate pipeline step (evidence-to-events bridge) out of scope for this ADR.

⸻

## Decision

- **Module name:** Implement the new service under `app/extractor/` (not under `app/services/extractor.py`) to avoid confusion with the existing HTML extractor. The HTML extractor remains at `app/services/extractor.py` unchanged. HTML text extraction (strip HTML, nav/footer, ~8k limit) is implemented in `app/services/extractor.py` and is aligned with Issue #12.
- **No SignalEvent write in this step:** The Extractor is in-memory only (or produces structured_payload for the Evidence Store). Converting Core Event candidates into `SignalEvent` rows and company resolution is a follow-up pipeline step, not part of the Extractor service.
- **Core taxonomy only:** Event types emitted by the Extractor are validated against core taxonomy (same set as core signal_ids used as event types). Unknown event types are rejected.
- **Source-backed:** All extracted fields and events are mapped to source_refs/source_ids. Aligned with SignalForge Architecture Contract §4 (LLM Boundary Rules).

⸻

## Consequences

- **Positive:** Clear separation between HTML extraction and entity/event extraction; no regression to Scout or Evidence Store when Extractor is disabled; single place for core event type validation.
- **Negative:** Two different “extractor” concepts in the codebase (HTML vs evidence); readers must distinguish `app/extractor` from `app/services/extractor`.
- **Evidence-to-events follow-up:** Any future step that writes SignalEvent rows from extractor output must enforce workspace (and optionally pack) when resolving company and writing events (see docs/discovery_scout.md).
- **References:** GitHub issue #277; Architecture Contract §4; docs/discovery_scout.md; docs/evidence-store.md.
