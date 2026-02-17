# Implementation Plan: GitHub Issue #32 — Error Handling

**Issue**: [Error handling](https://github.com/Disentangled-Tech/SignalForge/issues/32)

**Acceptance Criteria**:
- One company failure doesn't stop job
- Logged in job_runs
- Alert on failures in UI and email briefing

---

## Architecture Context (CURSOR_PRD.md)

The PRD Error Handling section states:

> Rules:
> - one company failure cannot stop a run
> - record company, step, and error message
> - store in job_runs table

The PRD Internal Job Endpoints section adds:

> Requirements:
> - create JobRun record
> - never crash server
> - return JSON status

---

## Current State Analysis

### 1. One company failure doesn't stop job

| Job Type | Implementation | Status |
|----------|---------------|--------|
| **Scan** (`run_scan_all`) | `scan_orchestrator.py`: per-company try/except; errors appended to list; job continues | ✅ Met |
| **Briefing** (`generate_briefing`) | `briefing.py`: per-company try/except; `logger.exception`; job continues | ✅ Met |
| **Company scan** (single) | `run_scan_company_with_job`: single company; failure stops that job | N/A (single-company) |

**Conclusion**: Both bulk jobs already implement "one company failure doesn't stop job."

---

### 2. Logged in job_runs

| Job Type | `error_message` populated? | `companies_processed` | Gap |
|----------|---------------------------|------------------------|-----|
| **Scan** | ✅ Yes — concatenated per-company errors | ✅ Yes | None |
| **Briefing** | ❌ No — cleared to `None` on success | ✅ Yes | **Partial failures not recorded** |

**Briefing gap**: When some companies fail (e.g., 3 of 5), the briefing job:
- Sets `status = "completed"`
- Sets `companies_processed = len(items)` (successful count)
- Sets `error_message = None` — **per-company failures are lost**

Per-company errors are only logged via `logger.exception`, not stored in `job_runs.error_message`.

**PRD requirement**: "record company, step, and error message" — implies storing per-company failures in job_runs.

---

### 3. Alert on failures in UI

| Location | Current behavior | Gap |
|----------|------------------|-----|
| **Settings** | Recent Job Runs table shows `status`, `error_message`, `companies_processed` | ✅ Failed jobs visible |
| **Briefing page** | Flash from `?error=` only when POST `/briefing/generate` raises | ❌ No alert for cron-triggered failures |
| **Company detail** | Shows "Last scan failed" for company-specific scan | ✅ Per-company scan failures visible |

**Gaps**:
- **Briefing page**: No indication when the last briefing job had failures (partial or full). User must go to Settings to see job_runs.
- **Briefing page**: When user clicks "Generate Now" and some companies fail, redirect shows generic "Briefing generation failed" only if the whole job raises; partial failures produce no user feedback.

---

### 4. Alert on failures in email briefing

| Scenario | Current behavior | Gap |
|----------|------------------|-----|
| Briefing email sent | Contains briefing items only | N/A |
| Some companies failed | Email still sent with successful items; no mention of failures | ❌ **No failure alert in email** |
| All companies failed | No items → `send_briefing_email` not called | ❌ No email at all; user unaware |

**Gap**: When briefing email is sent, there is no mention of partial failures (e.g., "2 of 5 companies could not be processed"). When all fail, no email is sent and the user has no notification.

---

## Gap Summary

| Criterion | Status | Action |
|-----------|--------|--------|
| One company failure doesn't stop job | ✅ Met | None |
| Logged in job_runs | ⚠️ Partial | Store per-company briefing failures in `error_message` |
| Alert in UI | ⚠️ Partial | Show failure alert on Briefing page; optionally Settings |
| Alert in email briefing | ❌ Missing | Add failure summary to briefing email when failures occurred |

---

## Implementation Plan

### Phase 1: Store per-company failures in job_runs (Briefing)

**File**: `app/services/briefing.py`

**Change**: When any company fails during briefing generation, collect error messages and persist them in `job.error_message` instead of clearing it.

```python
# In generate_briefing, replace the per-company loop:
errors: list[str] = []
for company in companies:
    try:
        item = _generate_for_company(db, company)
        if item is not None:
            items.append(item)
    except Exception as exc:
        msg = f"Company {company.id} ({company.name}): {exc}"
        logger.exception("Briefing generation failed for company %s (id=%s)", company.name, company.id)
        errors.append(msg)

job.finished_at = datetime.now(timezone.utc)
job.status = "completed"
job.companies_processed = len(items)
job.error_message = "; ".join(errors) if errors else None  # <-- change: keep errors
db.commit()
```

**Tests**: Update `tests/test_briefing.py` to assert that when some companies fail, `job.error_message` contains the failure details.

---

### Phase 2: Alert on failures in UI

#### 2a. Briefing page: show last job status

**Files**: `app/api/briefing_views.py`, `app/templates/briefing/today.html`

**Change**: Query the most recent briefing JobRun for today (or most recent). If it has `status == "failed"` or `error_message` is set, pass it to the template and display an alert.

```python
# In _render_briefing, add:
from app.models.job_run import JobRun
latest_briefing_job = (
    db.query(JobRun)
    .filter(JobRun.job_type == "briefing")
    .order_by(JobRun.started_at.desc())
    .first()
)
# Pass: latest_job_run=latest_briefing_job
```

Template: If `latest_job_run` exists and (`status == "failed"` or `error_message`), show a flash-style alert: "Last briefing had failures. See Settings → Recent Job Runs for details." or similar.

**Consideration**: Avoid cluttering the briefing page. A subtle banner or link to Settings may suffice.

#### 2b. Briefing generate POST: surface partial failures

**File**: `app/api/briefing_views.py`

**Change**: `generate_briefing` returns `list[BriefingItem]` but the view does not use it. We could have `generate_briefing` return a richer result (e.g., `(items, errors)`) or have the view query the latest JobRun after generation to get `error_message`. Simpler: have `generate_briefing` return a small result object or tuple `(items, error_summary)`, and the view redirect with `?error=...` when `error_summary` is non-empty.

**Simpler approach**: After `generate_briefing(db)` returns, query the latest briefing JobRun (we know it was just created). If `error_message` is set, redirect to `/briefing?error=Some+companies+failed.+See+Settings+for+details` (or a shorter message).

```python
# In briefing_generate:
generate_briefing(db)
# Fetch the job that was just created
latest = db.query(JobRun).filter(JobRun.job_type == "briefing").order_by(JobRun.started_at.desc()).first()
if latest and latest.error_message:
    return RedirectResponse(
        url=f"/briefing?error=Partial+failures.+See+Settings+for+details",
        status_code=303,
    )
return RedirectResponse(url="/briefing", status_code=303)
```

**Note**: On full exception, the existing `except` block already redirects with `?error=Briefing+generation+failed`. No change needed there.

---

### Phase 3: Alert on failures in email briefing

**File**: `app/services/email_service.py`

**Change**: Add an optional `failure_summary` parameter to `send_briefing_email`. When provided (e.g., "2 of 5 companies could not be processed: Company A (id=1): ..."), append a section to the email body (HTML and text) such as:

```
---
Note: Some companies could not be processed:
- Company A (id=1): <error>
- Company B (id=2): <error>
```

**File**: `app/services/briefing.py`

**Change**: When calling `send_briefing_email`, pass `failure_summary` when `errors` is non-empty. Build a concise summary (e.g., first 500 chars of `job.error_message` or a truncated list).

**Edge case**: When all companies fail (`items` is empty), `send_briefing_email` is not called. Options:
- **A)** Send a "briefing failed" email when `items` is empty but `errors` is non-empty (requires recipient + SMTP). This notifies the user even when no briefing content was generated.
- **B)** Do not send email when no items; user must check Settings. Simpler, but no proactive alert.

**Recommendation**: Implement **A** — send a short "Briefing generation completed with failures" email when there are errors, even if `items` is empty. Subject: "SignalForge Briefing — Failures (no items generated)" or similar. Body: list of errors. This satisfies "alert on failures in email briefing."

---

## Schema / Model Changes

**JobRun model**: No schema change. `error_message` (Text) already exists and can hold concatenated errors (same pattern as scan job).

---

## Implementation Checklist

| Task | Phase | Priority | Breaking? |
|------|-------|----------|-----------|
| 1. Store per-company briefing failures in `job.error_message` | 1 | High | No |
| 2. Update briefing tests for partial-failure error_message | 1 | High | No |
| 3. Briefing page: show alert when last job had failures | 2a | Medium | No |
| 4. Briefing generate POST: redirect with error when partial failures | 2b | Medium | No |
| 5. Email: add `failure_summary` param to `send_briefing_email` | 3 | Medium | No (additive) |
| 6. Briefing: pass failure summary to email; send failure-only email when no items | 3 | Medium | No |

---

## Test Plan

1. **Unit tests**
   - `test_briefing.py`: When 2 of 3 companies fail, assert `job.error_message` contains both failure messages; `job.status == "completed"`; `job.companies_processed == 1`.
   - `test_briefing.py`: When all companies fail, assert `job.error_message` is set; `job.companies_processed == 0`.
   - `test_email_service.py` (if exists) or new: `send_briefing_email` with `failure_summary` includes it in body.

2. **Integration**
   - Run briefing with one company that will fail (e.g., mock LLM to raise); verify JobRun has `error_message`.
   - Trigger briefing via POST; verify redirect with `?error=...` when partial failures.
   - Enable email; run briefing with failures; verify email contains failure summary.

3. **Regression**
   - Full test suite: `pytest`
   - Snyk code scan per project rules

---

## Out of Scope / Deferred

- **Scan job**: Already stores errors in `job.error_message`. No change.
- **Real-time notifications**: PRD forbids WebSockets; no push notifications.
- **Separate `job_run_errors` table**: Overkill for V1; concatenated string is sufficient.
- **Retry logic for failed companies**: Not in scope for this issue.

---

## Summary

| Criterion | Before | After |
|-----------|--------|-------|
| One company failure doesn't stop job | ✅ | ✅ |
| Logged in job_runs | ⚠️ Briefing cleared errors | ✅ Briefing stores per-company errors |
| Alert in UI | ⚠️ Settings only | ✅ Briefing page + generate redirect |
| Alert in email briefing | ❌ | ✅ Failure summary in email; failure-only email when no items |

No breaking changes to existing functionality. All changes are additive or fix underspecified behavior.
