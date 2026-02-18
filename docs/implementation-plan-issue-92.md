# Implementation Plan: GitHub Issue #92 — Readiness Delta Alert Job

**Issue**: [Implement readiness delta alert job](https://github.com/Disentangled-Tech/SignalForge/issues/92)  
**Status**: Implemented

---

## Summary

Implements the `alertScanDaily` job (v2-spec §12) that:
- Compares each company's latest readiness snapshot to the previous day
- Creates `Alert` when |delta| >= threshold (default 15)
- Prevents duplicate alerts per company + as_of
- Payload includes old_composite, new_composite, delta, as_of

Instability flag deferred to follow-up (Option C).

---

## Files Changed

| File | Action |
|------|--------|
| `app/services/readiness/alert_scan.py` | Created — `run_alert_scan()` |
| `app/services/readiness/__init__.py` | Added `run_alert_scan` export |
| `app/api/internal.py` | Added `POST /internal/run_alert_scan` |
| `app/config.py` | Added `ALERT_DELTA_THRESHOLD` (default 15) |
| `scripts/run_alert_scan.py` | Created — CLI script |
| `tests/test_alert_scan.py` | Created — 7 unit tests |
| `tests/test_internal.py` | Added TestRunAlertScan (4 tests) |

---

## Usage

### CLI
```bash
python scripts/run_alert_scan.py
```

### Internal endpoint (cron)
```bash
curl -X POST https://host/internal/run_alert_scan \
  -H "X-Internal-Token: $INTERNAL_JOB_TOKEN"
```

### Cron order
1. `POST /internal/run_score` (or `run_score_nightly.py`)
2. `POST /internal/run_alert_scan` (or `run_alert_scan.py`)
3. `POST /internal/run_briefing`

---

## Configuration

- `ALERT_DELTA_THRESHOLD` (env): Default 15. Alert when |delta| >= this value.
