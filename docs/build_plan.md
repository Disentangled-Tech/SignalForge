# SignalForge 2-Week Plan (Linked to GitHub Issues)

**Generated:** 2026-02-25  
**Scope:** Bugs, ingestion, ORE API, ESL alerts, explainability

---

## Overview

| Week | Focus | Sessions |
| --- | --- | --- |
| Week 1 | Bugs + Ingestion + Scan All | 5 |
| Week 2 | ORE API + ESL Alerts + Explainability | 5 |

---

## Week 1

### Session 1: Fix Scan All UX & Validation

**Issue:** [#162 — Validate that Scan All actually scans and surfaces companies](https://github.com/Disentangled-Tech/SignalForge/issues/162)

| Task | Files | Outcome |
| --- | --- | --- |
| Improve empty-state message when `scan_change_denom == 0` | `app/templates/settings/index.html` | Clear guidance when no scan data |
| Set `job.error_message` when no companies have `website_url` | `app/services/scan_orchestrator.py` | Explicit error for empty scan |
| Add integration test | `tests/test_scan_orchestrator.py` | Test: company with URL → scan → JobRun with `companies_processed >= 1` |

**Verify:** Add company with URL, run Scan All, check Settings shows scan metrics.

---

### Session 2: Ingest "Does Nothing" (Production Adapters)

**Issue:** [#210 — Injest should find and add new companies to watch](https://github.com/Disentangled-Tech/SignalForge/issues/210) (typo: "Injest")

**Note:** #210 overlaps with [#134 — Implement Crunchbase and Product Hunt ingestion adapters](https://github.com/Disentangled-Tech/SignalForge/issues/134) (from `docs/github-issues-out-of-scope-89.md`). #210 is the user-facing bug; #134 is the implementation.

| Task | Files | Outcome |
| --- | --- | --- |
| Implement one production adapter (Crunchbase or Product Hunt) | `app/ingestion/adapters/crunchbase_adapter.py` (new) | `_get_adapters()` returns real adapter when configured |
| Wire adapter into `run_ingest_daily` | `app/services/ingestion/ingest_daily.py` | Production adapters used when env configured |
| Add unit test for adapter | `tests/test_ingestion_adapter.py` | Adapter returns valid RawEvents |

**Suggested issue:** If #134 does not exist, create: *Implement Crunchbase and Product Hunt ingestion adapters* (from `docs/github-issues-out-of-scope-89.md`).

**Verify:** Run ingest, confirm `signal_events` and new companies appear.

---

### Session 3: Hourly Cron for Ingestion

**Issue:** [#135 — Set up hourly cron job for signal ingestion](https://github.com/Disentangled-Tech/SignalForge/issues/135) (from docs; may need creation)

| Task | Files | Outcome |
| --- | --- | --- |
| Add `scripts/run_ingest.sh` | `scripts/run_ingest.sh` (new) | Script calls `POST /internal/run_ingest` with token |
| Document cron setup | `README.md` or `docs/pipeline.md` | Instructions for Cloudways/cron |
| Wire cron config | Cloudways / cron | Hourly `POST /internal/run_ingest` |

**Verify:** Wait 1 hour, check `job_runs` for `job_type='ingest'`.

---

### Session 4: ORE API Endpoint

**Issue:** [#122 — Pack-Aware Outreach Recommendation Endpoint](https://github.com/Disentangled-Tech/SignalForge/issues/122)

| Task | Files | Outcome |
| --- | --- | --- |
| Add `GET /api/outreach/recommendation/{company_id}` | `app/api/outreach.py` | Returns recommendation or 404 |
| Support optional `as_of` and `pack_id` | `app/api/outreach.py` | Pack-scoped recommendations |
| Add schema for response | `app/schemas/outreach.py` | `OutreachRecommendationResponse` |

**Verify:** `GET /api/outreach/recommendation/1` returns recommendation or 404.

---

### Session 5: Scan All Integration Test

**Issue:** [#162](https://github.com/Disentangled-Tech/SignalForge/issues/162) (continued)

| Task | Files | Outcome |
| --- | --- | --- |
| Add integration test for Scan All → JobRun → Settings | `tests/test_scan_orchestrator.py`, `tests/test_settings_views.py` | Test asserts full flow |
| Add test for `get_scan_change_rate_30d` with completed scan | `tests/test_scan_metrics.py` | Non-None rate when scan has data |

**Verify:** `pytest tests/test_scan_orchestrator.py tests/test_scan_metrics.py -v`

---

## Week 2

### Session 6: Pack-Scoped Signal Alert System

**Issue:** [#137 — Implement Pack-Scoped Signal Alert System](https://github.com/Disentangled-Tech/SignalForge/issues/137)

| Task | Files | Outcome |
| --- | --- | --- |
| Extend alert scan for signal events (not just readiness delta) | `app/services/readiness/alert_scan.py` | New alert type from `SignalEvent` |
| Pack-scope alerts | `alert_scan.py` | Alerts filtered by pack |
| Add tests | `tests/test_alert_scan.py` | Signal-event alerts covered |

**Verify:** Run alert scan, check `Alert` table for new alert type.

---

### Session 7: Deterministic Explainability Renderer

**Issue:** [#194 — Implement Deterministic Explainability Renderer with Evidence Linking](https://github.com/Disentangled-Tech/SignalForge/issues/194)

| Task | Files | Outcome |
| --- | --- | --- |
| Add explainability renderer module | `app/services/explainability/` (new) | Uses pack `explainability_templates` |
| Link to evidence via `evidence_event_ids` → `SignalEvent.url` | `app/services/explainability/renderer.py` | Evidence URLs in output |
| Integrate into briefing and outreach review | `app/api/briefing_views.py`, `app/services/outreach_review.py` | Rendered "Why You're Seeing This" |
| PII redaction (emails, phones) | `app/services/explainability/` | Redact before render |

**Depends on:** [#187 — Refactor LeadCard UI to Use Pack Taxonomy Labels](https://github.com/Disentangled-Tech/SignalForge/issues/187) (taxonomy labels).

**Verify:** Briefing and outreach review show standardized explainability with evidence links.

---

### Session 8: LeadCard Pack Taxonomy Labels

**Issue:** [#187 — Refactor LeadCard UI to Use Pack Taxonomy Labels](https://github.com/Disentangled-Tech/SignalForge/issues/187)

| Task | Files | Outcome |
| --- | --- | --- |
| Replace hardcoded labels with taxonomy | `app/api/briefing_views.py`, templates | `event_type_to_label(ev, pack)` |
| Add sensitivity badge from ESL | `app/templates/briefing/today.html` | Badge from `sensitivity_level` |
| Works for CTO and bookkeeping packs | — | Pack-agnostic labels |

**Verify:** Briefing shows pack-driven labels and sensitivity badge.

---

### Session 9: Instability / Sensitivity System

**Issue:** [#148 — Replace Instability Flag with Pack-Aware Sensitivity & Context System](https://github.com/Disentangled-Tech/SignalForge/issues/148)

| Task | Files | Outcome |
| --- | --- | --- |
| Add `readiness_instability` alert type | `app/services/readiness/alert_scan.py` | Multiple large deltas in short window |
| Or add `instability: true` to `readiness_jump` payload | `alert_scan.py` | Per [docs/issues/ISSUE-instability-flag.md](issues/ISSUE-instability-flag.md) |
| Wire sensitivity from taxonomy | `app/services/esl/` | `signal.sensitivity` from pack |

**Verify:** Volatile snapshots produce instability alerts.

---

### Session 10: ORE Draft Versioning

**Issue:** [#123 — Allow Regenerating Outreach Drafts (Versioned)](https://github.com/Disentangled-Tech/SignalForge/issues/123)

| Task | Files | Outcome |
| --- | --- | --- |
| Add versioning to `OutreachRecommendation.draft_variants` | `app/models/outreach_recommendation.py` | Version history |
| Add regenerate endpoint or UI action | `app/api/outreach.py` or views | Regenerate and store new version |
| Preserve previous versions | Migration if needed | No data loss on regenerate |

**Verify:** Regenerate draft, confirm new version stored and old preserved.

---

## Suggested New Issues (Work Not Yet Tracked)

| Suggested Issue | Purpose |
| --- | --- |
| **Scan All: Improve empty-state UX when no companies with URLs** | Split UX work from #162 so the bug fix is separate from messaging. |
| **Add integration test: Scan All → JobRun → Settings display** | Test coverage for #162. |
| **Document and script cron setup for run_ingest** | If #135 does not exist, create it from `docs/github-issues-out-of-scope-89.md`. |
| **Implement Crunchbase/Product Hunt ingestion adapters** | If #134 does not exist, create it (same source). |

---

## Redundant or Overlapping Issues

| Issue | Flag | Recommendation |
| --- | --- | --- |
| **#210** | Overlaps with #134 | #210 = "Ingest doesn't do anything"; #134 = implement adapters. Treat #210 as the bug and #134 as the implementation. Close #210 when #134 is done, or merge into #134. |
| **#186 vs #191** | Overlap | #186: active pack selection; #191: pack switching semantics. #191 is more detailed. Consider closing #186 and tracking under #191, or make #186 a sub-task of #191. |
| **#187 vs #194** | Related | #187: taxonomy labels; #194: explainability renderer. #194 depends on #187. Keep both; do #187 before #194. |
| **#177** | Prerequisite, not 2-week work | Audit of CTO assumptions. Do before #178/#179. Defer from this 2-week plan. |
| **#178** | Large | Full CTO pack extraction. Defer from this 2-week plan. |
| **#180–185** (Bookkeeping) | Blocked | Need #178/#179 first. Defer from this 2-week plan. |
| **#196** | Beta-only | Feedback instrumentation. Lower priority than bugs and core flows. Defer. |

---

## Summary Table

| Session | Issue | Title |
| --- | --- | --- |
| 1 | [#162](https://github.com/Disentangled-Tech/SignalForge/issues/162) | Validate Scan All + UX improvements |
| 2 | [#210](https://github.com/Disentangled-Tech/SignalForge/issues/210) / [#134](https://github.com/Disentangled-Tech/SignalForge/issues/134) | Production ingestion adapter |
| 3 | [#135](https://github.com/Disentangled-Tech/SignalForge/issues/135) | Hourly cron for ingestion |
| 4 | [#122](https://github.com/Disentangled-Tech/SignalForge/issues/122) | ORE API endpoint |
| 5 | [#162](https://github.com/Disentangled-Tech/SignalForge/issues/162) | Scan All integration tests |
| 6 | [#137](https://github.com/Disentangled-Tech/SignalForge/issues/137) | Pack-scoped signal alerts |
| 7 | [#194](https://github.com/Disentangled-Tech/SignalForge/issues/194) | Explainability renderer |
| 8 | [#187](https://github.com/Disentangled-Tech/SignalForge/issues/187) | LeadCard pack taxonomy labels |
| 9 | [#148](https://github.com/Disentangled-Tech/SignalForge/issues/148) | Instability / sensitivity system |
| 10 | [#123](https://github.com/Disentangled-Tech/SignalForge/issues/123) | ORE draft versioning |

**Deferred (outside 2 weeks):** #177, #178, #179, #180–185, #186, #191, #193, #196, #197.
