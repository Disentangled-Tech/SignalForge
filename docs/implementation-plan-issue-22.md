# Implementation Plan: GitHub Issue #22 — Select Top Companies

**Issue**: [Select top companies](https://github.com/Disentangled-Tech/SignalForge/issues/22)  
**Rules**:
- Activity within 14 days
- Highest scores

**Acceptance Criteria**:
- Exactly top 5 returned
- No duplicates in the last 7 days

---

## Architecture Context (CURSOR_PRD.md)

The PRD Daily Briefing section states:

> Once per day:
> 1. Select companies with activity in the last 14 days
> 2. Sort by score descending
> 3. Select top 5
> 4. Generate briefing entries
> 5. Store briefing
> 6. Optionally email to operator

The pipeline is:

```
companies → signals → analysis → scoring → briefing → outreach draft
```

`select_top_companies` in `app/services/briefing.py` is the function that implements steps 1–3. It is called by `generate_briefing`, which is triggered by:
- `POST /briefing/generate` (UI)
- `POST /internal/run_briefing` (cron)

---

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| `select_top_companies` | Implemented | `app/services/briefing.py` |
| Activity window | 14 days | `_ACTIVITY_WINDOW_DAYS = 14` |
| Dedup window | 7 days | `_DEDUP_WINDOW_DAYS = 7` |
| Activity filter | `last_scan_at >= cutoff` OR `company_id IN (recent signals)` | `briefing.py:59-62` |
| Dedup filter | Exclude `company_id IN (briefed in last 7 days)` | `briefing.py:63` |
| Sort | `cto_need_score DESC NULLS LAST` | `briefing.py:64` |
| Limit | `limit=5` (default) | `briefing.py:65` |

---

## Gap Analysis: Issue #22 vs Current Implementation

| Requirement | Current State | Gap |
|--------------|---------------|-----|
| **Activity within 14 days** | ✅ Implemented | None — `last_scan_at` or recent signal qualifies |
| **Highest scores** | ✅ Implemented | None — ordered by `cto_need_score` desc |
| **Exactly top 5 returned** | ⚠️ Partial | **Gap** — If fewer than 5 companies qualify (activity + not recently briefed), we return fewer. The AC "exactly top 5" is ambiguous: it could mean (a) return up to 5, or (b) always return 5 (padding with lower-scoring companies). PRD says "Select top 5" — interpreted as **up to 5**, not "exactly 5 always". No change needed unless product explicitly requires padding. |
| **No duplicates in the last 7 days** | ✅ Implemented | None — `recently_briefed_ids` excludes companies with `BriefingItem` in last 7 days |

### Interpretation of "Exactly top 5"

- **Strict**: Always return 5 companies. If fewer qualify, pad with next-best (even if outside 14-day window or recently briefed). This would contradict "no duplicates in last 7 days" and "activity within 14 days."
- **Practical**: Return the top 5 *among qualifying* companies. If only 3 qualify, return 3. This matches PRD and existing behavior.

**Recommendation**: Treat "exactly top 5" as **up to 5** — the top 5 from the qualifying pool. No padding. If product later requires "always 5," that would need a separate decision (e.g., relax activity or dedup).

---

## Edge Cases and Potential Gaps

### 1. Companies Without Analysis (No Score)

**Current behavior**: Companies with `cto_need_score = NULL` are included if they have activity and are not recently briefed. They sort last (`nullslast()`).

**Issue #22**: "Highest scores" implies we want scored companies first. Companies without analysis cannot produce a briefing ( `_generate_for_company` skips them). Including them in the top 5 wastes slots.

**Recommendation**: Require at least one `AnalysisRecord` per company. This ensures:
- We only consider companies that can produce a briefing
- "Highest scores" is meaningful (all candidates have scores)

**Implementation**: Add a filter: `Company.id.in_(companies_with_analysis)` or `EXISTS (SELECT 1 FROM analysis_records WHERE company_id = companies.id)`.

### 2. Stored vs Recomputed Score

**Current behavior**: `select_top_companies` uses `Company.cto_need_score` (stored). The company detail view recomputes from analysis and repairs if wrong.

**Gap**: If `cto_need_score` is stale (e.g., custom weights changed, analysis updated but score not yet persisted), ordering may be wrong. `get_display_scores_for_companies` uses recomputed scores for the list view.

**Options**:
- **A**: Keep using stored score. Simpler; repair happens on company detail view and on `run_scan_company_full`. Stale ordering is a minor risk.
- **B**: Use `get_display_scores_for_companies`-style recomputation in `select_top_companies`. More accurate but adds a join/subquery and custom-weight lookup.

**Recommendation**: **Option A** for V1. Stored score is updated by `score_company` during scan. If product observes ordering issues, we can switch to Option B.

### 3. `last_scan_at` NULL Handling

**Current filter**: `(Company.last_scan_at >= activity_cutoff) | (Company.id.in_(recent_signal_ids))`

When `last_scan_at` is NULL, `NULL >= activity_cutoff` evaluates to NULL/unknown in SQL, so the first condition is false. The company qualifies only if it appears in `recent_signal_ids`. This is correct: companies with no scan must have a recent signal to qualify.

**No change needed.**

### 4. Empty `recent_signal_ids` Subquery

If no signals exist in the activity window, `recent_signal_ids` is empty. `Company.id.in_([])` is false for all companies. Companies qualify only via `last_scan_at >= activity_cutoff`. Correct.

**No change needed.**

---

## Implementation Tasks

### Task 1: Require Analysis for Top-Company Selection (Recommended)

**Goal**: Exclude companies without analysis so we don't waste top-5 slots on companies that will be skipped anyway.

**File**: `app/services/briefing.py`

**Change**: Add a filter so only companies with at least one `AnalysisRecord` are considered.

```python
# Sub-query: company IDs with at least one analysis (needed for briefing generation).
companies_with_analysis = (
    db.query(AnalysisRecord.company_id)
    .distinct()
    .subquery()
)

companies = (
    db.query(Company)
    .filter(Company.id.in_(companies_with_analysis))  # NEW
    .filter(
        (Company.last_scan_at >= activity_cutoff)
        | (Company.id.in_(recent_signal_ids))
    )
    .filter(~Company.id.in_(recently_briefed_ids))
    .order_by(Company.cto_need_score.desc().nullslast())
    .limit(limit)
    .all()
)
```

**Rationale**: Aligns selection with what `generate_briefing` can actually produce. "Highest scores" applies only to scorable companies.

### Task 2: Tests (TDD)

**File**: `tests/test_briefing.py`

**New/updated tests**:

1. **`test_select_top_companies_excludes_companies_without_analysis`**  
   - Create companies with activity, some with analysis and some without.  
   - Assert only companies with analysis appear in the result.

2. **`test_select_top_companies_exactly_up_to_limit`**  
   - When 5+ qualify, assert exactly 5 returned.  
   - When 2 qualify, assert 2 returned (no padding).

3. **`test_select_top_companies_no_duplicates_in_7_days`**  
   - Create a company with a BriefingItem in the last 7 days.  
   - Assert it is excluded even if it has the highest score and activity.

4. **`test_select_top_companies_activity_within_14_days`**  
   - Company with `last_scan_at` 20 days ago and no recent signals: excluded.  
   - Company with `last_scan_at` 5 days ago: included.

5. **`test_select_top_companies_ordered_by_score_desc`**  
   - Companies with scores 90, 70, 50: assert order is 90, 70, 50.

**Existing tests**: `test_returns_companies_from_query`, `test_respects_limit`, `test_returns_empty_when_no_companies` — update mocks if the query structure changes (e.g., extra subquery).

### Task 3: Integration Test with Real DB (Optional)

Use `tests/conftest.py` session/engine if available. Seed companies, signals, analyses, briefing items; call `select_top_companies`; assert counts and exclusion rules. Low priority if unit tests with mocks are sufficient.

### Task 4: Document "Exactly Top 5" Semantics

**File**: `app/services/briefing.py` (docstring)

Clarify:

```python
"""Select the top N companies for today's briefing.

Criteria:
1. Activity within 14 days (last_scan_at OR signal created_at).
2. At least one AnalysisRecord (required for briefing generation).
3. Sorted by cto_need_score descending (nulls last).
4. Exclude companies with a BriefingItem in the last 7 days.

Returns up to `limit` companies (default 5). Fewer may be returned if
fewer qualify. No padding.
"""
```

---

## Verification Checklist

- [ ] Activity within 14 days — `last_scan_at` or recent signal; unchanged.
- [ ] Highest scores — order by `cto_need_score` desc; unchanged.
- [ ] Exactly top 5 — up to 5 from qualifying pool; no padding.
- [ ] No duplicates in last 7 days — exclude recently briefed; unchanged.
- [ ] Companies without analysis excluded — new filter; prevents wasted slots.
- [ ] Existing tests pass — update mocks if query structure changes.
- [ ] New tests cover edge cases — analysis requirement, limit, dedup, activity, ordering.
- [ ] Snyk scan — run on modified code per project rules.
- [ ] No breaking changes to `generate_briefing` or API contracts.

---

## Summary

| Task | Effort | Risk |
|------|--------|------|
| Add analysis-required filter | Low | Low |
| Add/update tests | Low | None |
| Update docstring | Trivial | None |

**Total**: ~1–2 hours. The main functional change is excluding companies without analysis. The rest of the logic already satisfies Issue #22.

---

## Out of Scope (Defer Unless Requested)

- Using recomputed scores instead of stored `cto_need_score` for ordering.
- "Always return 5" padding when fewer than 5 qualify.
- Configurable activity/dedup windows (currently constants are sufficient).
