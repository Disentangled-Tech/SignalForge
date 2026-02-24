# Legacy-vs-Pack Parity Harness — Tracking

**Status**: Phase 2 complete. Parity harness must pass before merge.  
**Reference**: rules/TDD_rules.md, `.cursor/plans/scoring_engine_pack_refactor_ebb7e057.plan.md`

**Phase 2 (Issue #174, CTO Pack Extraction)**: Added `minimum_threshold`, `disqualifier_signals` to pack scoring. Fractional CTO pack uses empty disqualifiers for parity. Full parity harness passes: `compute_readiness(events, pack=None)` == `compute_readiness(events, pack=cto)` for all fixture scenarios. `TestReadinessEnginePackParameter` skips removed.

**Phase 4 (Issue #175)**: ESL decision moved from explain JSONB to dedicated columns
(`esl_decision`, `esl_reason_code`, `sensitivity_level`) on engagement_snapshots.
JobRun tracks `companies_esl_suppressed` for score jobs. Briefing/ORE prefer columns
over explain when reading.

**ORE behavior change (Phase 4)**: `get_weekly_review_companies` now excludes entities
where `esl_decision == "suppress"`. Previously ORE could return suppressed companies;
they are now filtered out. Briefing (`get_emerging_companies`) already filtered
suppressed in Phase 3.

## Overview

The Legacy-vs-Pack Parity Harness ensures that when migrating from the legacy pipeline (pre-pack, `pack_id=NULL`) to the pack pipeline (fractional_cto_v1), we do not introduce subtle breakage. The harness runs the same fixed fixture through both paths and asserts parity.

## Implementation

| Test File | Tests |
|-----------|-------|
| `tests/test_legacy_pack_parity.py` | `TestFromPackFractionalCtoMatchesDefaults`, `TestReadinessParitySameEventsPackNoneVsCto`, `TestEmergingCompaniesParityPackVsLegacy`, `TestIngestDeriveScoreParity` |

**Phase 2 parity tests** (must pass before merge):
- `test_from_pack_minimum_threshold_defaults_to_zero`, `test_from_pack_disqualifier_signals_empty_for_cto`
- `test_same_events_pack_none_vs_cto_produces_same_composite` (no skip)

## Fixture Dataset (TDD_rules)

- **Fixed as_of**: `date(2099, 6, 15)` for determinism
- **Companies**: 5 companies with distinct domains
- **Events**: Canonical event_types (funding_raised, job_posted_engineering, cto_role_posted)
- **Snapshots**: Same composite/esl for pack (pack_id=cto) and legacy (pack_id=NULL)

## Assertions

- **from_pack parity**: `from_pack(fractional_cto_v1)` yields same values as module constants
- **Readiness parity**: `compute_readiness(events, pack=None)` == `compute_readiness(events, pack=cto)`
- **Entity set**: `set(pack_entity_ids) == set(legacy_entity_ids) == expected`
- **Ordering**: Same OutreachScore ordering (64, 60, 58, 54, 35)

## Follow-ups

- [ ] Extend harness to compare `select_top_companies` (legacy) vs `get_emerging_companies` (pack) when both paths are fully wired (requires aligned fixture: AnalysisRecord + snapshots; `test_get_emerging_companies_pack_returns_companies_with_snapshots` added for pack path)
- [ ] Add ESL decision and sensitivity label assertions when those fields are exposed in test fixtures (per TDD_rules follow-ups)
- [ ] Add outreach draft constraints assertion (tone, required elements, no forbidden phrases)
