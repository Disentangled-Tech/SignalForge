# Implementation Plan: GitHub Issue #108 — Weekly Outreach Review Endpoint

**Issue**: [Implement Weekly Outreach Review Endpoint](https://github.com/Disentangled-Tech/SignalForge/issues/108)  
**Status**: Implemented

---

## Summary

Implements `GET /api/outreach/review` that returns top OutreachScore companies for weekly review:
- Sorted by OutreachScore DESC
- Limited to configurable weekly max (`weekly_review_limit`, default 5)
- Excludes cooldown companies (60-day + 180-day declined per Issue #109)
- Includes explain block per company

---

## Files Changed

| File | Action |
|------|--------|
| `app/services/outreach_review.py` | Created — `get_weekly_review_companies()`, `get_latest_snapshot_date()` |
| `app/schemas/outreach.py` | Created — `OutreachReviewItem`, `OutreachReviewResponse` |
| `app/api/outreach.py` | Created — `GET /api/outreach/review` |
| `app/main.py` | Modified — register outreach router |
| `tests/test_outreach_review.py` | Created — 11 unit tests |

---

## API Usage

### Endpoint

```
GET /api/outreach/review
```

**Query parameters**:
- `date` (optional): Snapshot date (YYYY-MM-DD). Default: latest available.
- `limit` (optional): Max companies to return (1–20). Default: `weekly_review_limit` from config.

**Authentication**: Required (same as `/api/companies`, `/api/watchlist`).

### Response

```json
{
  "as_of": "2026-02-18",
  "companies": [
    {
      "company_id": 1,
      "company_name": "Example Co",
      "website_url": "https://example.com",
      "outreach_score": 72,
      "explain": {
        "readiness": { "dimensions": {...}, "top_events": [...] },
        "engagement": { "cadence_blocked": false, ... }
      }
    }
  ]
}
```

---

## Configuration

Uses existing settings:
- `WEEKLY_REVIEW_LIMIT` (env): Max companies in review (default 5)
- `OUTREACH_SCORE_THRESHOLD` (env): Min OutreachScore to include (default 30)

---

## Non-Breaking Guarantee

- `get_emerging_companies` unchanged (briefing UI still shows cooldown companies with Observe Only)
- New endpoint is additive only
- No changes to existing briefing, watchlist, or company endpoints
