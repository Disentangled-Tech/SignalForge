# Pipeline: Lead feed last_seen from core + M6/M7 docs and tests (Refs #287)

**Suggested PR title:** `Pipeline: Lead feed last_seen from core SignalInstances (M5) + M6 tests & M7 docs (#287)`

Implements **Milestone M5** of the core-vs-pack refactor and includes **M6 regression coverage** and **M7 documentation** (Refs [Issue #287](https://github.com/Disentangled-Tech/SignalForge/issues/287)). Lead feed projection uses core SignalInstances for `last_seen` when `core_pack_id` is set; projection key `(workspace_id, pack_id)` is unchanged.

## Summary

| Milestone | Scope |
|-----------|--------|
| **M5** | Lead feed: `_batch_last_seen_for_entities` accepts optional `core_pack_id`; when set, last_seen comes from core pack instances. `run_update_lead_feed`, `run_backfill_lead_feed`, `score_nightly`, and `lead_feed_writer` pass `core_pack_id`. Backward compatible: when core pack missing, pack-scoped last_seen used. |
| **M6** | Tests: daily aggregation and ingestion-scoring assert derive → core SignalInstances, score → pack-scoped snapshots; parity harness test for run_derive(no pack) → run_score(with pack). |
| **M7** | Docs: `pipeline.md`, `CORE_VS_PACK_RESPONSIBILITIES.md`, and SignalForge Architecture Contract updated for derive/score/core; section numbering in CORE_VS_PACK. |

## Key Changes

### Projection builder
- **`app/services/lead_feed/projection_builder.py`**: `_batch_last_seen_for_entities(db, entity_ids, pack_id, core_pack_id=None)`. When `core_pack_id` is set, filter by `SignalInstance.pack_id == core_pack_id`; when None, keep legacy (pack_id or NULL). `upsert_lead_feed_from_snapshots` and `build_lead_feed_from_snapshots` accept and pass `core_pack_id`.

### Callers
- **`app/services/lead_feed/run_update.py`**: `get_core_pack_id(db)`; pass to `build_lead_feed_from_snapshots` in `run_update_lead_feed` and `run_backfill_lead_feed`. Comment clarifying behavior when core pack not installed.
- **`app/services/readiness/score_nightly.py`**: Pass `core_pack_id` to `upsert_lead_feed_from_snapshots`.
- **`app/pipeline/lead_feed_writer.py`**: `get_core_pack_id(db)`; pass to `build_lead_feed_from_snapshots`.

### Documentation (M7)
- **`docs/pipeline.md`**: M3 note (score reads core SignalInstances); M5 note (lead_feed last_seen from core when core pack installed).
- **`docs/CORE_VS_PACK_RESPONSIBILITIES.md`**: Derive section updated (runs without pack, writes to core); new Score section (core input, pack interpretation); section renumbering.
- **`docs/SignalForge Architecture Contract`**: One line that score reads core signals and applies pack interpretation.

### Tests
- **`tests/test_lead_feed.py`**: `test_build_last_seen_from_core_instances_when_core_pack_id_provided`; `test_build_last_seen_from_pack_scoped_when_core_pack_id_none`; import `SignalInstance`; formatting.
- **`tests/test_daily_aggregation.py`**: M6 assertions in `test_daily_aggregation_full_run_with_test_adapter_asserts_ranked_output` (core pack_id for SignalInstance, workspace pack_id for ReadinessSnapshot); `_FailingAdapter` retained for provider-failure test; formatting.
- **`tests/test_ingestion_scoring_integration.py`**: M6 assertion that ReadinessSnapshots have pack_id set; formatting.
- **`tests/test_legacy_pack_parity.py`**: M6 integration test `test_parity_run_derive_no_pack_then_score_with_pack_produces_composite`.

## Files Modified

| Path | Change |
|------|--------|
| `app/services/lead_feed/projection_builder.py` | `core_pack_id` in last_seen batch + public APIs |
| `app/services/lead_feed/run_update.py` | Resolve and pass `core_pack_id`; comments |
| `app/services/readiness/score_nightly.py` | Pass `core_pack_id` to upsert_lead_feed_from_snapshots |
| `app/pipeline/lead_feed_writer.py` | Resolve and pass `core_pack_id` |
| `docs/pipeline.md` | M3 and M5 notes |
| `docs/CORE_VS_PACK_RESPONSIBILITIES.md` | Derive/Score sections + renumbering (M7) |
| `docs/SignalForge Architecture Contract` | Score reads core + pack interpretation (M7) |
| `tests/test_lead_feed.py` | M5 tests (core + pack-scoped last_seen); formatting |
| `tests/test_daily_aggregation.py` | M6 assertions; _FailingAdapter kept; formatting |
| `tests/test_ingestion_scoring_integration.py` | M6 pack_id assertion; formatting |
| `tests/test_legacy_pack_parity.py` | M6 parity test (derive no pack → score with pack) |

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
