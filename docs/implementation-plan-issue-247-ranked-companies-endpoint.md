# Implementation Summary: Ranked Companies Endpoint (Issue #247)

**Issue**: [#247 — Expose endpoint to fetch ranked companies for Daily Briefing](https://github.com/Disentangled-Tech/SignalForge/issues/247)  
**Plan**: Approved implementation plan (ranked_companies_endpoint_734e460b)  
**Date**: 2026-02-26

---

## Executive Summary

`GET /api/companies/top` exposes ranked companies for the Daily Briefing UI. It reuses existing `get_emerging_companies_for_briefing` logic with pack-scoped scoring, recommendation bands, and top signals. No schema changes; additive endpoint only.

---

## Phases Completed

### Milestone 1: Schema + Service (PR 1)

| Step | Files | Status |
|------|-------|--------|
| 1.1 | `app/schemas/ranked_companies.py` | `RankedCompanyTop`, `RankedCompaniesResponse` |
| 1.2 | `app/services/ranked_companies.py` | `get_ranked_companies_for_api` |
| 1.3 | `tests/test_ranked_companies.py` | Service unit tests |

### Milestone 2: Endpoint (PR 2)

| Step | Files | Status |
|------|-------|--------|
| 2.1 | `app/api/companies.py` | `GET /top` route (before `/{company_id}`) |
| 2.2 | Workspace access | `validate_uuid_param_or_422`, `_require_workspace_access` when multi_workspace_enabled |
| 2.3 | `tests/test_ranked_companies.py` | API tests |

### Milestone 3: Polish (PR 3)

| Step | Status |
|------|--------|
| 3.1 | `since` param (optional as_of override) |
| 3.2 | `limit` bounds (1–100, default 10) |
| 3.3 | Snyk scan |

### Milestone 4: Cleanup and Documentation (PR 4)

| Step | Files | Status |
|------|-------|--------|
| 4.1 | `app/api/companies.py` | OpenAPI docstrings for `GET /api/companies/top` |
| 4.2 | `docs/implementation-plan-issue-247-ranked-companies-endpoint.md` | This document |
| 4.3 | Code cleanup | Consistent patterns with briefing/companies API |

---

## API Reference

### GET /api/companies/top

**Auth**: Required (Bearer token or session cookie).

**Query params**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `since` | date (YYYY-MM-DD) | today | Snapshot date for ranking |
| `limit` | int (1–100) | 10 | Max companies to return |
| `workspace_id` | UUID | — | When multi_workspace_enabled; scopes results |

**Response**:

```json
{
  "companies": [
    {
      "company_id": 1,
      "company_name": "Acme Inc",
      "website_url": "https://acme.example.com",
      "composite_score": 85,
      "recommendation_band": "HIGH_PRIORITY",
      "top_signals": ["Cto Role Posted", "Funding Raised"],
      "momentum": 70,
      "complexity": 65,
      "pressure": 60,
      "leadership_gap": 40
    }
  ],
  "total": 1
}
```

**Empty DB**: Returns `{"companies": [], "total": 0}`. No exception.

**Workspace scoping**: When `multi_workspace_enabled` and `workspace_id` provided, invalid UUID → 422; user lacks access → 403.

---

## Verification Checklist

| Check | Command / Result |
|-------|------------------|
| Tests | `pytest tests/ -v -W error` |
| Coverage | `pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=75 -W error` |
| Linter | `ruff check` — zero errors |
| Snyk | Code scan on `app/api/companies.py`, `app/services/ranked_companies.py`, `app/schemas/ranked_companies.py` — 0 issues |
| OpenAPI | `/docs` and `/redoc` render correctly |

---

## Config Notes

- Uses `outreach_score_threshold` from settings (same as briefing).
- Uses `weekly_review_limit`-style cap via `limit` param (max 100).
- Pack resolution: `get_pack_for_workspace(db, workspace_id)` when multi_workspace; else default pack.

---

## Gotchas for Future Maintainers

1. **Route order**: `GET /top` must be defined before `GET /{company_id}` to avoid path collision.
2. **Dual-path**: Service prefers `lead_feed` when populated; falls back to ReadinessSnapshot + EngagementSnapshot join.
3. **Fractional CTO flow**: Unchanged; this endpoint is additive.

---

## Risk Assessment

- **Low**: Additive; fractional CTO flow intact.
- **Route collision**: Mitigated by defining `/top` before `/{company_id}`.
- **Cross-tenant leakage**: Mitigated by `_require_workspace_access` when multi_workspace_enabled.
