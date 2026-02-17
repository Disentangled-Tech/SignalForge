# Implementation Plan: GitHub Issue #14 — SignalRecord Storage

**Issue**: [SignalRecord storage](https://github.com/Disentangled-Tech/SignalForge/issues/14)  
**Store**: `raw_text`, `hash`, `timestamp`  
**Acceptance Criteria**:
- Duplicate page not re-saved
- Last activity timestamp updates

---

## Architecture Context (CURSOR_PRD.md)

SignalRecord fits into the PRD pipeline:

```
companies → signals → analysis → scoring → briefing → outreach draft
```

**Company Scan** (PRD § System Behavior):
1. Fetch homepage HTML
2. Attempt common paths: /blog, /news, /careers, /jobs
3. Extract readable text
4. **Deduplicate using content hash**
5. **Store SignalRecord**

This plan addresses the storage and deduplication behavior without changing the pipeline. All orchestration remains in Python; no LLM, agent, or external system changes.

---

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| SignalRecord model | Exists | `app/models/signal_record.py` |
| Deduplication | Implemented (company_id + content_hash) | `app/services/signal_storage.py` |
| Hash storage | `content_hash` (SHA-256 of content_text) | `app/models/signal_record.py` |
| Timestamp | `created_at` only | `app/models/signal_record.py` |
| Raw text | Stored as `content_text` | `app/models/signal_record.py` |
| Raw HTML | Stored as `raw_html` (optional) | `app/models/signal_record.py` |
| Last activity | Company-level `last_scan_at` only | `app/models/company.py`, `app/services/signal_storage.py` |

---

## Gap Analysis

### Issue #14 Requirements vs Current Implementation

| Requirement | Current State | Gap |
|-------------|---------------|-----|
| **raw_text** | `content_text` exists (extracted page text) | ✅ **No gap** — `content_text` is the raw extracted text. Issue uses "raw_text" as a label; we keep `content_text` as the column name for consistency. |
| **hash** | `content_hash` exists (SHA-256 of content_text) | ✅ **No gap** — Already stored and used for deduplication. |
| **timestamp** | `created_at` exists | ⚠️ **Partial gap** — Issue AC: "Last activity timestamp updates." We have `created_at` on SignalRecord and `last_scan_at` on Company. The AC implies: when a page is re-visited (duplicate), we should still update a "last activity" timestamp. Currently, duplicates do **not** update any timestamp. |
| **Duplicate page not re-saved** | Dedup by company_id + content_hash | ✅ **No gap** — Implemented; duplicates return `None` and are not stored. |
| **Last activity timestamp updates** | `last_scan_at` updated only on **new** signal | ❌ **Gap** — When a duplicate is detected, we skip storage and do **not** update `last_scan_at`. The AC suggests that re-visiting a page (even if duplicate) should count as "activity" and update the last-activity timestamp. |

### Data Preservation (Do Not Eliminate)

The plan must **integrate** existing data, not remove it:

| Existing Field | Action |
|----------------|--------|
| `content_text` | Keep — this is the "raw_text" (extracted page text). |
| `content_hash` | Keep — this is the "hash". |
| `created_at` | Keep — creation timestamp. |
| `raw_html` | Keep — optional raw HTML; useful for debugging/reprocessing. |
| `source_url`, `source_type` | Keep — required for display and source attribution. |
| `company_id` | Keep — FK. |

**No columns or data will be dropped.**

---

## Implementation Tasks

### 1. Add `last_activity_at` to SignalRecord (Optional Enhancement)

**Goal**: Per-signal "last seen" timestamp for when a duplicate page is re-visited.

**Rationale**: The AC "Last activity timestamp updates" can be satisfied in two ways:

- **Option A (Recommended)**: Update `company.last_scan_at` when a duplicate is detected. Simpler; aligns with "last scan" semantics.
- **Option B**: Add `last_activity_at` to SignalRecord and update it when a duplicate is re-visited. More granular but adds schema change.

**Recommendation**: **Option A** — update `company.last_scan_at` on duplicate detection. No schema change, minimal code change, satisfies "last activity timestamp updates" at the company level.

### 2. Update `store_signal` to Refresh Last Activity on Duplicate

**Goal**: When a duplicate (same company_id + content_hash) is detected, still update `company.last_scan_at` to "now".

**File**: `app/services/signal_storage.py`

**Current behavior**:
```python
if existing is not None:
    logger.debug(...)
    return None  # No last_scan_at update
```

**New behavior**:
```python
if existing is not None:
    logger.debug(...)
    # AC: Last activity timestamp updates — even for duplicates
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is not None:
        company.last_scan_at = datetime.now(timezone.utc)
    db.commit()
    return None
```

**Impact**:
- Duplicate page visits now count as "activity" for briefing selection (14-day window).
- Company list "Last Scan" column reflects most recent scan run, including when only duplicates were found.

### 3. Tests (TDD)

**File**: `tests/test_signal_storage.py`

**New test**:
```python
def test_duplicate_signal_updates_last_scan_at(self):
    """Duplicate signal still updates company.last_scan_at (AC: last activity timestamp)."""
    company = _make_company()
    company.last_scan_at = None
    existing = MagicMock(spec=SignalRecord)
    existing.id = 99
    db = _make_query_mock(existing_record=existing, company=company)

    result = store_signal(
        db,
        company_id=1,
        source_url="https://acme.example.com/blog",
        source_type="blog",
        content_text="Duplicate content",
    )

    assert result is None
    db.add.assert_not_called()
    # AC: last activity timestamp updates
    assert company.last_scan_at is not None
    db.commit.assert_called_once()
```

**Update existing test**:
- `test_duplicate_signal_skipped` — currently asserts `db.commit.assert_not_called()`. With the new behavior, we *do* call `commit` when updating `last_scan_at`. Adjust assertion: `db.add.assert_not_called()` remains; `db.commit.assert_called_once()` when company exists.

### 4. Edge Case: Company Not Found on Duplicate

When duplicate is detected and `company` is `None` (e.g. orphaned FK), we should **not** call `db.commit()` — there is nothing to persist. Only update and commit when `company is not None`.

**Logic**:
```python
if existing is not None:
    logger.debug(...)
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is not None:
        company.last_scan_at = datetime.now(timezone.utc)
        db.commit()
    return None
```

### 5. Schema / Migration

**No migration required** for the recommended approach. We are only changing service logic, not the SignalRecord or Company schema.

---

## Verification Checklist

- [ ] Duplicate page not re-saved — existing behavior preserved; `store_signal` returns `None`, no new row.
- [ ] Last activity timestamp updates — `company.last_scan_at` updated on duplicate when company exists.
- [ ] No data eliminated — all existing columns (`content_text`, `content_hash`, `created_at`, `raw_html`, etc.) unchanged.
- [ ] Briefing activity window — companies with only duplicate scans in last 14 days now qualify (via `last_scan_at`).
- [ ] Tests pass — new test for duplicate + last_scan_at; existing tests updated as needed.
- [ ] Snyk scan — run on modified code per project rules.

---

## Alternative: Per-Signal `last_activity_at` (Out of Scope for Minimal Fix)

If product later needs per-signal "last seen" timestamps (e.g. to show "this page was re-visited 3 days ago"), we would:

1. Add migration: `ALTER TABLE signal_records ADD COLUMN last_activity_at TIMESTAMP`.
2. On duplicate: `existing.last_activity_at = now()` and commit.
3. Backfill: `last_activity_at = created_at` for existing rows.

This is **not** required to satisfy the current AC and adds schema complexity. Defer unless explicitly requested.

---

## Summary

| Task | Effort | Risk |
|------|--------|------|
| Update `store_signal` to set `last_scan_at` on duplicate | Low | Low |
| Add test for duplicate + last_scan_at | Low | None |
| Adjust `test_duplicate_signal_skipped` assertions | Low | None |

**Total**: ~30 minutes. No schema changes. No data loss. Satisfies both acceptance criteria.
