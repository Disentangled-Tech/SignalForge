# minimum_threshold Enforcement (Issue #174)

**Status**: Documented; enforcement not yet implemented.  
**Reference**: v2-spec §4.5, scoring engine pack refactor Phase 2.

## Overview

`minimum_threshold` is an optional pack scoring config value that defines the minimum **raw composite readiness (R)** a company must have to appear in briefing and lead-feed surfaces. When a pack defines `minimum_threshold > 0`, companies with `R < minimum_threshold` should be excluded from those surfaces.

## Where It Comes From

- **Pack config**: `packs/<pack_id>/scoring.yaml` → `minimum_threshold: <int>` (default: 0)
- **Engine**: `from_pack()` in `app/services/readiness/scoring_constants.py` parses it; `build_explain_payload()` in `readiness_engine.py` includes it in the explain payload when non-zero
- **Storage**: `ReadinessSnapshot.explain["minimum_threshold"]` when pack defines it (non-zero); omitted when 0 or default

## Current State: Where It Is NOT Enforced

The following surfaces **do not** currently enforce `minimum_threshold`:

| Surface | Entry Point | Current Filter | minimum_threshold |
|---------|-------------|----------------|-------------------|
| **Emerging Companies** (briefing page) | `get_emerging_companies()` in `app/services/briefing.py` | `outreach_score_threshold` (OutreachScore = round(R × ESL)) | ❌ Not enforced |
| **Briefing data** (HTML + JSON API) | `get_briefing_data()` in `app/api/briefing_views.py` | Calls `get_emerging_companies()` with `outreach_score_threshold` | ❌ Not enforced |
| **Weekly review / Outreach API** | `get_weekly_review_companies()` in `app/services/outreach_review.py` | `outreach_score_threshold` | ❌ Not enforced |
| **Briefing item generation** | `select_top_companies()` in `app/services/briefing.py` | `cto_need_score` (different metric) | ❌ Not enforced |
| **Lead-feed projection** | `build_lead_feed_from_snapshots()`, `upsert_lead_feed_from_snapshots()` | Excludes entities with `rs.composite < min_thresh` when pack defines `minimum_threshold > 0` | ✅ Enforced |

## Where It SHOULD Be Enforced (Future)

When implementing enforcement:

1. **`get_emerging_companies()`** (`app/services/briefing.py`): After loading `(ReadinessSnapshot, EngagementSnapshot)` pairs, exclude companies where `rs.composite < min_thresh` and `min_thresh` comes from `rs.explain.get("minimum_threshold")` when present and > 0. Pack-scoped: use the pack’s explain for that snapshot.

2. **`get_weekly_review_companies()`** (`app/services/outreach_review.py`): Same logic—exclude companies where `rs.composite < minimum_threshold` from pack explain when pack defines it.

3. **`get_briefing_data()`** (`app/api/briefing_views.py`): No direct change needed if `get_emerging_companies()` enforces it; briefing data inherits the filter.

## Relationship to outreach_score_threshold

| Concept | Definition | Used By |
|---------|-------------|---------|
| **minimum_threshold** | Pack-defined minimum **R** (raw composite). Companies with R below this are excluded. | Not yet enforced |
| **outreach_score_threshold** | Global/operator setting (default 30). Minimum **OutreachScore** = round(R × ESL). | `get_emerging_companies`, `get_weekly_review_companies` |

Both filters apply when enforcement is implemented: a company must have `R >= minimum_threshold` (from pack) **and** `OutreachScore >= outreach_score_threshold` (from config).

## v2-spec Alignment

v2-spec §14 acceptance criteria: *"Daily briefing endpoint returns top 10 companies (>=60) sorted"* — the 60 is the intended minimum R for briefing. Packs can set `minimum_threshold: 60` to enforce this; fractional_cto_v1 uses `minimum_threshold: 0` for parity with legacy.

## Implementation Notes

- **Pack-scoped**: Each snapshot’s `explain` is written with the pack used for scoring. Use `rs.explain.get("minimum_threshold")`; when absent or 0, no R-based exclusion.
- **Backward compatibility**: Packs with `minimum_threshold: 0` or omitted behave as today (no R-based exclusion).
- **Cadence-blocked**: `get_emerging_companies` currently includes cadence-blocked companies even when below `outreach_score_threshold`. Decide whether `minimum_threshold` should also apply to cadence-blocked (likely yes for consistency).
