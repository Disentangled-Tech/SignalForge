# LLM Event Interpretation (Issue #281)

One-pager: input, output, validation, and reuse of the LLM-based event classification layer.

## Purpose

Classify **raw content** (e.g. diffs, evidence text) into **Core Event candidates** with a strict schema and taxonomy. No new event types are introduced; all output is validated against the [core taxonomy](app/core_taxonomy/taxonomy.yaml).

## Input

- **Content:** Raw text to classify (e.g. diff summary, evidence bundle text).
- **Evidence (optional):** List of `EvidenceItem` (url, quoted_snippet, timestamp_seen, etc.) for mapping `source_refs` (0-based indices) so events are source-backed.

For the **Diff-Based Monitor**, input is a structured `ChangeEvent` (page_url, diff_summary, timestamp); the interpretation step turns it into a list of `CoreEventCandidate`.

## Output

- **List of `CoreEventCandidate`:** Each item has `event_type` (must be a core taxonomy `signal_id`), `confidence`, `source_refs`, and optional `title`, `summary`, `url`, `event_time`. Optional snippet can be carried in interpretation-specific schemas (e.g. `InterpretationOutputItem`) and then converted to `CoreEventCandidate` for extractor/verification.

## Validation and invariants

- **No new types:** Every `event_type` is validated with `is_valid_core_event_type` (core taxonomy). Unknown types are **dropped**, not stored. The interpretation layer never invents event types.
- **Schema:** Output must conform to the CoreEventCandidate contract; interpretation modules (e.g. `app/monitor/interpretation.py`) parse LLM JSON and build only valid candidates.
- **Token logging:** When the LLM provider exposes token usage or latency, the interpretation layer logs it for audit/calibration.

## Reuse

- **Scout:** When optional event interpretation is enabled, evidence (or hypothesis + evidence) can be passed to the interpretation layer; the resulting `core_event_candidates` are merged into `raw_extraction` and passed to the existing extractor. See [discovery_scout.md](discovery_scout.md).
- **Diff-Based Monitor (Issue #280):** The monitor produces `ChangeEvent`s from page diffs; `interpret_change_event` in `app/monitor/interpretation.py` calls the LLM and returns `list[CoreEventCandidate]` for persistence or downstream pipelines.

## Key code

| Area | Location |
| ---- | -------- |
| Schemas | `app/interpretation/schemas.py` — `InterpretationInput`, `InterpretationOutputItem`, `InterpretationOutput` |
| Monitor interpretation | `app/monitor/interpretation.py` — `interpret_change_event(ChangeEvent, llm_provider) → list[CoreEventCandidate]` |
| Validation | `app/extractor/validation.py` — `is_valid_core_event_type`; `app/core_taxonomy/loader.py` — `get_core_signal_ids()` |
| Core event shape | `app/schemas/core_events.py` — `CoreEventCandidate` |

## Calibration

Calibration tests (`tests/test_interpretation_calibration.py`) ensure:

- All returned `event_type` values are in the core taxonomy.
- No new event types are returned (invalid types are dropped).
- With fixed input and mock LLM, the set of returned event types is deterministic and a subset of the taxonomy.

With a real LLM, some variance across reruns is acceptable; the important invariant is that **every** returned event type remains in the core taxonomy.

## References

- [ADR-011](../rules/ADR-011-LLM-Event-Interpretation.md), [discovery_scout.md](discovery_scout.md), [monitor.md](monitor.md), Architecture Contract §4.
