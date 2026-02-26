# Pipeline: Lead feed last_seen from core SignalInstances (Refs #287 — M5)

Implements **Milestone M5** of the core-vs-pack refactor (Refs [Issue #287](https://github.com/Disentangled-Tech/SignalForge/issues/287)). Projection builder uses core SignalInstances for `last_seen` when `core_pack_id` is set; projection key `(workspace_id, pack_id)` is unchanged.

## Summary

| Milestone | Scope |
|-----------|--------|
| **M5** | Lead feed: `_batch_last_seen_for_entities` accepts optional `core_pack_id`; when set, last_seen comes from core pack instances. `run_update_lead_feed`, `run_backfill_lead_feed`, `score_nightly`, and `lead_feed_writer` pass `core_pack_id`. Backward compatible: when core pack missing, pack-scoped last_seen used. |

## Key Changes

### Projection builder
- **`app/services/lead_feed/projection_builder.py`**: `_batch_last_seen_for_entities(db, entity_ids, pack_id, core_pack_id=None)`. When `core_pack_id` is set, filter by `SignalInstance.pack_id == core_pack_id`; when None, keep legacy (pack_id or NULL). `upsert_lead_feed_from_snapshots` and `build_lead_feed_from_snapshots` accept and pass `core_pack_id`.

### Callers
- **`app/services/lead_feed/run_update.py`**: `get_core_pack_id(db)`; pass to `build_lead_feed_from_snapshots` in `run_update_lead_feed` and `run_backfill_lead_feed`.
- **`app/services/readiness/score_nightly.py`**: Pass `core_pack_id` to `upsert_lead_feed_from_snapshots`.
- **`app/pipeline/lead_feed_writer.py`**: `get_core_pack_id(db)`; pass to `build_lead_feed_from_snapshots`.

### Documentation and tests
- **`docs/pipeline.md`**: Note that when core pack is installed, lead_feed `last_seen` is taken from core SignalInstances.
- **`tests/test_lead_feed.py`**: New `test_build_last_seen_from_core_instances_when_core_pack_id_provided`; import `SignalInstance`.

## Files Modified

| Path | Change |
|------|--------|
| `app/services/lead_feed/projection_builder.py` | `core_pack_id` in last_seen batch + public APIs |
| `app/services/lead_feed/run_update.py` | Resolve and pass `core_pack_id` |
| `app/services/readiness/score_nightly.py` | Pass `core_pack_id` to upsert_lead_feed_from_snapshots |
| `app/pipeline/lead_feed_writer.py` | Resolve and pass `core_pack_id` |
| `docs/pipeline.md` | M5 note for run_update_lead_feed |
| `tests/test_lead_feed.py` | New test + formatting |

## Backward Compatibility

- When `core_pack_id` is None (e.g. core pack not installed), `_batch_last_seen_for_entities` uses pack-scoped instances (pack_id or NULL). Behavior identical to pre-M5.
- Projection key remains `(workspace_id, pack_id, entity_id)`; no schema or key change.

## Verification

- [ ] All tests pass: `pytest tests/ -v -W error`
- [ ] Coverage: `pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=75 -W error`
- [ ] Linter: `ruff check` and `ruff format` on modified paths
- [ ] Snyk: Zero issues on changed app code

## References

- Plan: `.cursor/plans/pipeline_derive_core_score_pack_08ed0139.plan.md`
- Issue: #287 (linked; not closed by this PR)
