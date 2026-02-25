# Implement SignalScorer v0 (weights + recommendation bands)

Closes https://github.com/Disentangled-Tech/SignalForge/issues/242

## Summary

Implements Phases 2 and 3 of the SignalScorer v0 plan: adds recommendation bands (IGNORE / WATCH / HIGH_PRIORITY) to `fractional_cto_v1`, persists band in `ReadinessSnapshot.explain`, exposes bands in API/UI, and adds `recommendation_band` to the lead feed projection.

## Changes

### Phase 2: Pack config & persistence

**Pack config** (`packs/fractional_cto_v1/scoring.yaml`)
- Added `recommendation_bands`: `ignore_max: 34`, `watch_max: 69`, `high_priority_min: 70` (0–100 scale)

**Scoring constants** (`app/services/readiness/scoring_constants.py`)
- `_norm_recommendation_bands()` parses and validates bands
- `from_pack()` returns `recommendation_bands` in engine-compatible dict

**Pack schema** (`app/packs/schemas.py`)
- `_validate_scoring()` validates optional `recommendation_bands` (ignore_max, watch_max, high_priority_min, ordering)

**Signal scorer** (`app/services/signal_scorer.py`) — new
- `resolve_band(composite, pack)` returns `"IGNORE" | "WATCH" | "HIGH_PRIORITY"` or `None` when pack has no bands

**Snapshot writer** (`app/services/readiness/snapshot_writer.py`)
- After `compute_readiness`, calls `resolve_band()` and stores result in `result["explain"]["recommendation_band"]`

**Schemas** (`app/schemas/signals.py`, `app/schemas/briefing.py`)
- Added optional `recommendation_band: str | None` to `CompanySignalScoreRead` and `EmergingCompanyBriefing`

### Phase 3: API & UI exposure

**Score resolver** (`app/services/score_resolver.py`)
- `get_company_score_with_band()` — returns (score, band) for company detail
- `get_company_scores_and_bands_batch()` — batched scores + bands for company list

**Scoring** (`app/services/scoring.py`)
- `get_display_scores_with_bands()` — delegates to score resolver, returns (scores, bands)

**Views** (`app/api/views.py`)
- `companies_list`: uses `get_display_scores_with_bands`, passes `company_bands` to template
- `company_detail`: uses `get_company_score_with_band`, passes `recommendation_band` to template

**Briefing** (`app/api/briefing_views.py`, `app/api/briefing.py`)
- `get_briefing_data`: extracts `recommendation_band` from ReadinessSnapshot.explain
- API response includes `recommendation_band` in emerging_companies

**Templates**
- `companies/list.html`: band badge next to score when pack defines bands
- `companies/detail.html`: band badge in header
- `briefing/today.html`: band badge in emerging section

**Lead feed** (`app/models/lead_feed.py`, `app/services/lead_feed/projection_builder.py`, `app/services/lead_feed/query_service.py`)
- Added `recommendation_band` column to LeadFeed model
- Projection builder passes band from ReadinessSnapshot.explain
- Query service returns band in lead payload

### Migrations

- **`20260230_update_config_checksum_recommendation_bands.py`**: Updates `signal_packs.config_checksum` for fractional_cto_v1; fails explicitly if row missing
- **`20260231_add_lead_feed_recommendation_band.py`**: Adds nullable `recommendation_band` to lead_feed

### Tests

- **`tests/test_signal_scorer.py`**: `resolve_band` (pack=None, no bands, invalid bands, boundaries 34/35/69/70)
- **`tests/test_readiness_scoring_constants.py`**: `TestFromPackRecommendationBands`
- **`tests/test_legacy_pack_parity.py`**: `TestRecommendationBandParity`
- **`tests/test_score_nightly.py`**: Assertion that `rs.explain["recommendation_band"]` in ("IGNORE", "WATCH", "HIGH_PRIORITY")
- **`tests/test_briefing_api.py`**: `test_briefing_json_includes_recommendation_band`
- **`tests/test_briefing_views.py`**: `test_emerging_section_shows_recommendation_band_when_pack_defines`

## Out of scope (split to separate PR if desired)

- **NewsAPI adapter** (`app/ingestion/adapters/newsapi_adapter.py`, `ingest_daily.py`, `__init__.py`): Unrelated to SignalScorer; consider reverting or moving to a separate PR.

## Verification

- [ ] `pytest tests/ -v -W error`
- [ ] `pytest tests/ -v --cov=app --cov-fail-under=75 -W error`
- [ ] `alembic upgrade head`
- [ ] `ruff check` on modified files — clean
- [ ] Snyk — zero issues on signal_scorer, scoring_constants, snapshot_writer, score_resolver

## Risk

- **Low**: Additive; fractional CTO flow unchanged; band stored in existing JSONB `explain` and optional lead_feed column
