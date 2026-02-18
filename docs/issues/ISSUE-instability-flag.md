<!-- When creating this issue on GitHub, add the `enhancement` label -->

## Summary

Add an "Instability flag" alert type to surface companies whose readiness composite score shows repeated large swings over a short window. This was deferred from Issue #92 (Readiness Delta Alert Job) to a follow-up enhancement.

**Related:** Issue #92 (Readiness Delta Alert Job)

---

## Background

Issue #92 implements `readiness_jump` alerts when a single day-over-day delta crosses the threshold (default 15). The "Instability flag" would identify companies with **multiple** large deltas in a short period, indicating volatile or unstable scoring patterns.

---

## Implementation Options (from plan)

| Option | Description |
|--------|-------------|
| **A** | Add `alert_type="readiness_instability"` when a company has multiple large deltas in a short window (e.g., 3+ jumps in 14 days). Requires more logic and possibly new table/query. |
| **B** | Add a flag in the `readiness_jump` payload: `"instability": true` when delta is very large (e.g., >= 25) or when the previous delta was also large. |

---

## Acceptance Criteria

- [ ] Instability detection logic defined (Option A or B, or hybrid)
- [ ] Alerts created for companies meeting instability criteria
- [ ] Alerts are internal-only (not surfaced to end users)
- [ ] No duplicate instability alerts for same company/date
- [ ] Tests cover instability detection and deduplication

---

## Out of Scope (for this issue)

- External notification of instability alerts
- UI changes for instability display
