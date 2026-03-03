# LLM Event Interpretation (Issue #281)

One-pager for the LLM-based layer that classifies raw content into Core Event candidates.

## Input

- **Content:** Raw text to classify (e.g. diff summary, evidence text).
- **Evidence:** Optional list of evidence items for source_refs (0-based indices into evidence list).

## Output

- List of **CoreEventCandidate** (event_type, confidence, source_refs, optional title/summary/url/event_time). Each `event_type` must be from the core taxonomy; invalid types are dropped.

## Validation

- All output is validated with `is_valid_core_event_type`; no new event types are introduced.
- Core taxonomy is the single source of truth (`app/core_taxonomy/taxonomy.yaml`).

## Token logging

- Interpretation modules log token usage and latency when the LLM provider exposes them.

## Reuse

- **Scout (optional):** When interpretation is enabled, evidence is classified and passed as `raw_extraction` to the Extractor.
- **Diff Monitor (#280):** Change events (diff summary, URL) are interpreted to Core Event candidates; same schema and validation.

## References

- [ADR-011](../rules/ADR-011-LLM-Event-Interpretation.md), [discovery_scout.md](discovery_scout.md), [monitor.md](monitor.md), Architecture Contract §4.
