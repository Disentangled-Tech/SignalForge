# Pipeline: Derive Core, Score from Core Instances, ESL from Core Signal Set (Refs #287 — M2, M3, M4)

Implements **Milestones M2, M3, and M4** of the core-vs-pack refactor (Refs [Issue #287](https://github.com/Disentangled-Tech/SignalForge/issues/287)). Builds on **M1** (core pack sentinel + `get_core_pack_id`). Derive runs without a workspace pack and writes to core; score and ESL read from core instances and apply pack weights/rubric.

## Summary

| Milestone | Scope |
|-----------|--------|
| **M1** (included) | Core pack sentinel migration; `get_core_pack_id(db)` in `pack_resolver` |
| **M2** | Derive runs without pack; writes to core pack only; no `SignalEvent.pack_id` filter; executor/API allow `pack_id=None` for derive |
| **M3** | Score reads event list from core SignalInstances (evidence_event_ids / last_seen fallback); snapshot writer + score_nightly pass `core_pack_id`; fallback to pack-scoped SignalEvents when no core instances |
| **M4** | ESL signal set from core: `_get_signal_ids_for_company` uses `core_pack_id` when set; pack still used for policy; ORE pipeline documented as legacy path |

## Key Changes

### M1 — Core pack sentinel
- **Migration** `alembic/versions/20260226_add_core_pack_sentinel.py`: Inserts one row into `signal_packs` with `pack_id='core'`, `version='1'` (Issue #287).
- **`app/services/pack_resolver.py`**: `get_core_pack_id(db) -> UUID | None`.

### M2 — Derive without pack, write to core
- **`app/pipeline/deriver_engine.py`**: Uses `get_core_pack_id(db)`; writes all SignalInstances to core pack; no filter on `SignalEvent.pack_id` (processes all events with `company_id`); JobRun.pack_id is passed pack or core for audit.
- **`app/pipeline/executor.py`**: For `job_type == "derive"` and `pack_id is None`, passes `pack_str = None` (no workspace pack required).
- **API**: Run_derive returns 200 with status completed/skipped; no 400 when pack is missing (docs updated).

### M3 — Score from core instances
- **`app/services/readiness/event_resolver.py`**: `get_event_like_list_from_core_instances(db, company_id, as_of, core_pack_id)` builds event-like list from core SignalInstances (evidence_event_ids → SignalEvents; fallback to signal_id + last_seen).
- **`app/services/readiness/snapshot_writer.py`**: Optional `core_pack_id`; when set, uses core instances for event list; fallback to pack-scoped SignalEvents when empty (TODO: remove after backfill).
- **`app/services/readiness/score_nightly.py`**: `get_core_pack_id(db)`; passes `core_pack_id` into `write_readiness_snapshot` and (with M4) `write_engagement_snapshot`.

### M4 — ESL from core signal set
- **`app/services/esl/engagement_snapshot_writer.py`**: `_get_signal_ids_for_company(..., core_pack_id=None)`; when `core_pack_id` set, queries SignalInstance by core pack for signal set; pack still used for `resolve_pack` and `evaluate_esl_decision`. `compute_esl_from_context` and `write_engagement_snapshot` accept and pass `core_pack_id`.
- **`app/services/readiness/score_nightly.py`**: Passes `core_pack_id` to `write_engagement_snapshot`.
- **`app/services/ore/ore_pipeline.py`**: Comment that ORE uses legacy ESL path (pack-scoped); does not pass `core_pack_id`.

### Documentation and tests
- **`docs/pipeline.md`**: Derive “does not require a pack”; post-deploy note (run derive); ORE pipeline legacy ESL note.
- **`docs/ADR-001-Introduce-Declarative-Signal-Pack-Architecture.md`**: Amendment for Issue #287 (core pack_id; snapshots/feed unchanged).
- **Tests**: `conftest` adds `core_pack_id` fixture; deriver tests assert on core pack; new `test_esl_signal_set_from_core_instances_when_core_pack_id_provided`; ingestion/scoring integration and legacy parity updated for core.

## Files Modified / Added

| Path | Change |
|------|--------|
| `alembic/versions/20260226_add_core_pack_sentinel.py` | New (M1) |
| `app/pipeline/deriver_engine.py` | M2 |
| `app/pipeline/executor.py` | M2 |
| `app/services/pack_resolver.py` | M1 |
| `app/services/readiness/event_resolver.py` | M3 (new) |
| `app/services/readiness/snapshot_writer.py` | M3 |
| `app/services/readiness/score_nightly.py` | M3, M4 |
| `app/services/esl/engagement_snapshot_writer.py` | M4 |
| `app/services/ore/ore_pipeline.py` | M4 (comment) |
| `docs/pipeline.md` | M2, M4 |
| `docs/ADR-001-Introduce-Declarative-Signal-Pack-Architecture.md` | Amendment |
| `tests/conftest.py` | `core_pack_id` fixture |
| `tests/test_deriver_engine.py` | Core pack assertions; new test |
| `tests/test_engagement_snapshot_writer.py` | M4 test |
| `tests/test_ingestion_scoring_integration.py` | core_pack_id |
| `tests/test_internal.py` | run_derive no 400 |
| `tests/test_legacy_pack_parity.py` | Core assertions |
| `tests/test_pipeline.py` | derive pack_id=None |
| `tests/test_readiness_composite.py` | core_pack_id where needed |
| `tests/test_score_nightly.py` | core_pack_id |
| `tests/test_event_resolver.py` | M3 (new) |

## Backward Compatibility

- **Derive**: No longer requires a workspace pack; when core pack is missing, returns 200 skipped. Callers that relied on 400 for “no pack” now get 200 skipped.
- **Score**: When `core_pack_id` is None or core instances are empty, snapshot writer falls back to pack-scoped SignalEvents (M3 fallback).
- **ESL**: Callers that do not pass `core_pack_id` keep legacy behavior (signal set from pack_id). ORE pipeline intentionally remains on legacy path.
- **Snapshots**: ReadinessSnapshot and EngagementSnapshot remain keyed by `(company_id, as_of, pack_id)` with workspace pack_id; no schema change.

## Verification

- [ ] All tests pass: `pytest tests/ -v -W error`
- [ ] Coverage: `pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=75 -W error`
- [ ] Linter: `ruff check` and `ruff format` on modified paths — zero errors
- [ ] Snyk: Zero issues on changed app code
- [ ] Migration: `alembic upgrade head` succeeds (ensure target branch’s migration chain; if target has a different head, set `down_revision` of core pack sentinel migration accordingly before merge)

## Migration Note

- **Post-merge**: Run migration `20260226_core_pack_sentinel` if not already applied. Then run **derive** at least once (e.g. nightly job) so core signal instances exist; score will use them. Until then, score uses the SignalEvent fallback where core instances are missing.

## References

- Plan: `.cursor/plans/pipeline_derive_core_score_pack_08ed0139.plan.md`
- Issue: #287
