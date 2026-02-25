# Signal Scorer Phase 2: Recommendation Bands

References https://github.com/Disentangled-Tech/SignalForge/issues/242

## Summary

Implements Phase 2 of the SignalScorer v0 plan: adds recommendation bands (IGNORE / WATCH / HIGH_PRIORITY) to `fractional_cto_v1`, persists band in `ReadinessSnapshot.explain`, and exposes optional `recommendation_band` in `CompanySignalScoreRead`.

## Changes

### Pack config (`packs/fractional_cto_v1/scoring.yaml`)
- Added `recommendation_bands`: `ignore_max: 34`, `watch_max: 69`, `high_priority_min: 70` (0–100 scale)

### Scoring constants (`app/services/readiness/scoring_constants.py`)
- `_norm_recommendation_bands()` parses and validates bands
- `from_pack()` returns `recommendation_bands` in engine-compatible dict

### Pack schema (`app/packs/schemas.py`)
- `_validate_scoring()` validates optional `recommendation_bands` (ignore_max, watch_max, high_priority_min, ordering)

### Signal scorer (`app/services/signal_scorer.py`) — new
- `resolve_band(composite, pack)` returns `"IGNORE" | "WATCH" | "HIGH_PRIORITY"` or `None` when pack has no bands

### Snapshot writer (`app/services/readiness/snapshot_writer.py`)
- After `compute_readiness`, calls `resolve_band()` and stores result in `result["explain"]["recommendation_band"]`

### Schemas (`app/schemas/signals.py`)
- Added optional `recommendation_band: str | None` to `CompanySignalScoreRead`

### Migration
- **`alembic/versions/20260230_update_config_checksum_recommendation_bands.py`**: Updates `signal_packs.config_checksum` for fractional_cto_v1 after `recommendation_bands` added to scoring.yaml

### Tests
- **`tests/test_signal_scorer.py`**: `resolve_band` (pack=None, no bands, invalid bands, boundaries 34/35/69/70)
- **`tests/test_readiness_scoring_constants.py`**: `TestFromPackRecommendationBands`
- **`tests/test_legacy_pack_parity.py`**: `TestRecommendationBandParity`
- **`tests/test_score_nightly.py`**: Assertion that `rs.explain["recommendation_band"]` in ("IGNORE", "WATCH", "HIGH_PRIORITY")

## Verification

- [x] `pytest tests/ -v -W error`
- [x] `pytest tests/ -v --cov=app --cov-fail-under=75 -W error`
- [x] `alembic upgrade head`
- [x] `ruff check` on modified files — clean
- [x] Snyk — zero issues on signal_scorer, scoring_constants, snapshot_writer

## Risk

- **Low**: Additive; fractional CTO flow unchanged; band stored in existing JSONB `explain` column
