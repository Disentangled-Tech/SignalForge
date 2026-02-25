# Phase 1: Audit scoring_constants.from_pack() for CTO fallbacks

Closes Plan §5 (Phase 1 remaining work)

## Summary

Completes the Phase 1 Engine Abstraction audit: documents CTO-specific fallback behavior in `from_pack()` and adds a regression test to verify empty config returns fractional_cto_v1 defaults.

## Changes

### scoring_constants.py
- **`from_pack()` docstring**: Added "CTO-specific fallbacks" section documenting that when pack omits a section or provides empty/falsy value, we fall back to module constants (BASE_SCORES_*, CAP_*, etc.) which match fractional_cto_v1. Non-CTO packs must define their own base_scores, caps, decay, and suppressors to avoid inheriting CTO defaults.

### tests/test_readiness_scoring_constants.py
- **`TestFromPackEmptyReturnsCtoFallbacks`**: New test class verifying `from_pack({})` returns CTO fallbacks for base_scores, caps, composite_weights, and quiet_signal.

## Verification

- [ ] `pytest tests/test_readiness_scoring_constants.py tests/test_legacy_pack_parity.py -v -W error` — all pass
- [ ] `ruff check app/services/readiness/scoring_constants.py tests/test_readiness_scoring_constants.py` — clean

## Risk

- **None**: Documentation and test only; no behavior change.
