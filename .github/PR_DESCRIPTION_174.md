# Phase 2: CTO Pack Extraction (Closes #174)

## Summary

Implements Phase 2 of the scoring engine pack refactor: adds `minimum_threshold` and `disqualifier_signals` to pack scoring config, applies disqualifier logic in the readiness engine, and validates full parity between legacy (`pack=None`) and fractional CTO pack.

## Changes

### Pack config
- **`packs/fractional_cto_v1/scoring.yaml`**: Added `minimum_threshold: 0`, `disqualifier_signals: {}` (empty for parity)

### Scoring engine
- **`app/services/readiness/scoring_constants.py`**: `from_pack()` returns `minimum_threshold`, `disqualifier_signals`; added `_norm_disqualifier_signals()`; decay and suppressors from pack (Phase 1)
- **`app/services/readiness/readiness_engine.py`**: Added `_check_disqualifier_signals()`; when pack defines disqualifiers and event present in window, R=0; `disqualifiers_applied` in explain payload

### Documentation
- **`docs/MINIMUM_THRESHOLD_ENFORCEMENT.md`**: Documents where `minimum_threshold` is stored, where it is not yet enforced, and where it should be enforced (briefing/lead-feed)
- **`docs/ISSUE_LEGACY_PACK_PARITY_HARNESS.md`**: Updated for Phase 2 completion; parity harness must pass before merge

### Docstring references
- **`app/services/briefing.py`**, **`app/services/outreach_review.py`**: Note that `minimum_threshold` is not yet enforced; link to enforcement doc

## Testing

- `test_from_pack_minimum_threshold_defaults_to_zero`, `test_from_pack_disqualifier_signals_empty_for_cto`
- `test_same_events_pack_none_vs_cto_produces_same_composite` (no skip)
- `TestDisqualifierSignals`: disqualifier zeros R when pack defines it; empty preserves composite
- `TestFromPackMinimumThresholdAndDisqualifierSignals`: parsing
- Full parity harness passes

## Verification

- [x] Fractional CTO behavior identical (parity tests)
- [x] No schema changes
- [x] Ruff clean; Snyk zero issues on changed files
