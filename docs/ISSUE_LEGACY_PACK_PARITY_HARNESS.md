# Legacy-vs-Pack Parity Harness — Tracking

**Status**: Implemented (Phase 4 follow-up)  
**Reference**: rules/TDD_rules.md, `.cursor/plans/deriver_engine_pack-driven_implementation_459de0b6.plan.md`

## Overview

The Legacy-vs-Pack Parity Harness ensures that when migrating from the legacy pipeline (pre-pack, `pack_id=NULL`) to the pack pipeline (fractional_cto_v1), we do not introduce subtle breakage. The harness runs the same fixed fixture through both paths and asserts parity.

## Implementation

| Test File | Tests |
|-----------|-------|
| `tests/test_legacy_pack_parity.py` | `TestFromPackFractionalCtoMatchesDefaults`, `TestReadinessParitySameEventsPackNoneVsCto`, `TestEmergingCompaniesParityPackVsLegacy` |

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

- [ ] Extend harness to compare `select_top_companies` (legacy) vs `get_emerging_companies` (pack) when both paths are fully wired
- [ ] Add ESL decision and sensitivity label assertions when those fields are exposed in test fixtures
- [ ] Add outreach draft constraints assertion (tone, required elements, no forbidden phrases)
