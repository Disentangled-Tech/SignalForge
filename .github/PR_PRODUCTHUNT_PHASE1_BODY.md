# Product Hunt Adapter Completion (Phase 1)

References https://github.com/Disentangled-Tech/SignalForge/issues/243

## Summary

Implements Phase 1 of the Product Hunt LAUNCH Provider plan: extends the GraphQL query with `votesCount`, `commentsCount`, and `makers`; adds retry with exponential backoff for 429/5xx; updates docs to mark Product Hunt as implemented.

## Changes

### Adapter (`app/ingestion/adapters/producthunt_adapter.py`)
- **GraphQL query**: Added `votesCount`, `commentsCount`, `makers { name }` to post node selection
- **`_extract_makers()`**: New helper to parse makers from post node; defensive parsing for malformed data
- **`_post_node_to_raw_event()`**: Populates `raw_payload` with `votesCount`, `commentsCount`, `makers` when available
- **Retry**: `_fetch_page` retries up to 3 times on 429/5xx with exponential backoff (1s, 2s, 4s); logs warnings on retries; returns `([], False, None)` on final failure

### Tests (`tests/test_producthunt_adapter.py`)
- **`_make_post_node()`**: Extended with optional `votes_count`, `comments_count`, `makers`
- **`TestProductHuntRawPayloadMetadata`**: `test_producthunt_raw_payload_includes_votes_comments_makers`
- **`TestProductHuntRetry`**: `test_producthunt_retries_on_429_then_succeeds`, `test_producthunt_retries_exhausted_returns_empty`, `test_producthunt_api_failure_does_not_crash`

### Docs (`docs/ingestion-adapters.md`)
- **Overview**: "Planned" → "Implemented" for Product Hunt
- **Section**: "Product Hunt (Planned)" → "Product Hunt (Implemented)"; documented retry behavior and `raw_payload` fields

## Verification

- [x] `pytest tests/test_producthunt_adapter.py -v -W error` — 10 passed
- [x] `ruff check` on modified files — clean
- [x] Snyk — zero issues on adapter

## Risk

- **Low**: Adapter-only changes; no schema or core service changes; fractional CTO flow unchanged
