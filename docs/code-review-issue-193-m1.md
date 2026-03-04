# Code Review: Issue #193 M1 — pack_id NOT NULL (Workspace + Pack Scoping)

**Scope:** M1 implementation (pack_id NOT NULL on signal_events, readiness_snapshots, engagement_snapshots).  
**Reviewer:** Automated code review.  
**Date:** 2026-03-04.

---

## 1. Executive Summary

The migration **20260304_pack_id_not_null_issue_193** correctly backfills NULL `pack_id` and alters the three tables to NOT NULL. The **application layer is not yet fully aligned** with M1: ORM models still declare `pack_id` as nullable, query logic still includes legacy `pack_id IS NULL` branches, and `event_storage` does not resolve a default pack when `pack_id` is None. This review lists concrete fixes so that code matches the database and M1 intent.

---

## 2. Database vs ORM Consistency

| Table                 | Migration (DB)     | ORM model (current)                          | Risk |
|-----------------------|--------------------|----------------------------------------------|------|
| signal_events         | `pack_id` NOT NULL | `pack_id: Mapped[uuid.UUID \| None]`, nullable=True | Insert with `pack_id=None` raises at DB; type hints allow None. |
| readiness_snapshots   | `pack_id` NOT NULL | Same                                         | Same. |
| engagement_snapshots  | `pack_id` NOT NULL | Same                                         | Same. |

**Recommendation:** Update the three ORM models so that:

- `pack_id` is declared `Mapped[uuid.UUID]` (no `| None`) and `nullable=False`.
- Keep FK `ondelete="SET NULL"` only if product intent is to allow pack deletion and then handle/sanitize; otherwise consider documenting that deleting a pack with referencing rows will fail (as in the migration comment).

This keeps the ORM in sync with the DB and surfaces missing `pack_id` at the Python layer.

---

## 3. Unique Constraint on engagement_snapshots

The migration only backfills and sets NOT NULL. It does **not** change the unique constraint.

- **Current:** `UniqueConstraint("company_id", "as_of", name="uq_engagement_snapshots_company_as_of")`.
- **M1 plan:** Unique per (company_id, as_of, **pack_id**) to allow multiple packs per company/date.

If the product requirement is one snapshot per (company, as_of, pack), add a migration that:

1. Drops `uq_engagement_snapshots_company_as_of`.
2. Adds `UniqueConstraint("company_id", "as_of", "pack_id", name="uq_engagement_snapshots_company_as_of_pack")`.

Same idea applies to `readiness_snapshots` if the plan specifies a pack-scoped unique constraint there.

---

## 4. Query Logic — Legacy `pack_id IS NULL` Branches

After M1, no row in the three tables has `pack_id` NULL. Continuing to filter with `or_(..., pack_id.is_(None))` is unnecessary and can blur pack boundaries.

**Files still using pack_id IS NULL for the M1 tables:**

| File | Usage |
|------|--------|
| `app/services/score_resolver.py` | pack_filter uses `or_(ReadinessSnapshot.pack_id == pack_uuid, (ReadinessSnapshot.pack_id.is_(None)) & (pack_uuid == default_pack_uuid))` and similar in four places. |
| `app/services/esl/engagement_snapshot_writer.py` | pack_filter and event_pack_filter use `or_(..., pack_id.is_(None))`. |
| `app/services/readiness/snapshot_writer.py` | event_pack_filter uses `or_(SignalEvent.pack_id == pack_id, SignalEvent.pack_id.is_(None))`. |
| `app/services/readiness/score_nightly.py` | event_filters append `or_(SignalEvent.pack_id == resolved_pack_id, SignalEvent.pack_id.is_(None))`. |
| `app/services/outreach_review.py` | pack_match and pack_filter use NULL for RS/ES. |
| `app/services/briefing.py` | pack_match and pack_filter for RS/ES; AnalysisRecord still uses or_ with NULL (see below). |
| `app/services/lead_feed/query_service.py` | pack_filter for EngagementSnapshot; pack_match and pack_filter for RS/ES in two places. |
| `app/services/lead_feed/projection_builder.py` | pack_match and pack_filter for RS/ES. |
| `app/api/briefing_views.py` | pack_match and pack_filter for RS/ES. |

**Recommendation:** For **ReadinessSnapshot**, **EngagementSnapshot**, and **SignalEvent** only:

- Replace every pack condition with a single equality: `ReadinessSnapshot.pack_id == pack_id` (or `pack_uuid`), and similarly for the other two.
- When `pack_uuid`/`pack_id` is None (e.g. no default pack), either return no rows (e.g. `snapshot = None`, `snapshots = []`) or short-circuit before querying; do not use `pack_id.is_(None)` on these three tables.
- Remove now-unused `or_` imports where they are only used for these pack filters.

**Out of scope for M1 (keep as-is unless you have a separate migration):**

- **AnalysisRecord** in `briefing.py` and `views.py`: still nullable in DB; keeping `or_(AnalysisRecord.pack_id == pack_id, (AnalysisRecord.pack_id.is_(None)) & ...)` is correct until that table is migrated.
- **SignalInstance** in `projection_builder.py`: same; leave NULL handling until that table has a NOT NULL migration.

---

## 5. event_storage — Default Pack When pack_id Is None

**Current:** `store_signal_event(..., pack_id: UUID | None = None)` passes `pack_id` through to `SignalEvent(...)`. If the caller omits `pack_id`, the model receives `None` and, after M1, the insert will fail at the DB with NOT NULL violation.

**Recommendation:** Resolve a default when `pack_id` is None:

- At the start of `store_signal_event`, if `pack_id is None`, set `pack_id = get_default_pack_id(db)` (import from `app.services.pack_resolver`).
- If after that `pack_id is None` (no default pack in DB), log and return `None` (or raise a clear error) so no insert is attempted with NULL.
- Update the docstring to state that when `pack_id` is not provided, the default pack is used and that the function may return None if no default pack exists.

This keeps a single place for “legacy” callers (e.g. watchlist seeder) that do not pass pack_id and avoids NOT NULL violations.

---

## 6. Docstrings and Comments

- **score_resolver.py:** The docstring still says “pack_id matches (or NULL when pack is default)”. After removing NULL branches, change to: “Latest ReadinessSnapshot for company where pack_id matches.”
- **engagement_snapshot_writer.py:** Remove the comment “Treat pack_id IS NULL as default pack until backfill completes (Issue #189)” (and similar “legacy NULL” comments) once the code no longer uses `pack_id.is_(None)` for the M1 tables.

---

## 7. Security and Correctness

- **Pack scoping:** Relying only on `pack_id == <resolved_pack>` (and never matching NULL) keeps queries strictly pack-scoped and avoids accidentally including rows that “would have been” default pack. No new security issues were introduced; the change tightens scope.
- **Idempotency:** Migration backfill and NOT NULL are idempotent in the intended way (re-running migration after backfill is a no-op for data). No change needed.
- **Cross-tenant:** M1 does not introduce workspace_id; pack_id scoping remains the main isolation for these tables. Ensuring no NULL in queries aligns with that.

---

## 8. Tests

- Any test that **creates** `ReadinessSnapshot`, `EngagementSnapshot`, or `SignalEvent` must supply a non-null `pack_id` (e.g. `fractional_cto_pack_id` fixture or `get_default_pack_id(db)`), or the test will fail with NOT NULL violation after the migration is applied.
- Tests that **query** these tables and currently rely on “NULL means default pack” should be updated to pass an explicit pack_id (or default) and assert on that pack only.

---

## 9. Checklist (M1 Completion)

- [ ] ORM: `pack_id` non-optional and `nullable=False` on SignalEvent, ReadinessSnapshot, EngagementSnapshot.
- [ ] event_storage: Resolve default pack when `pack_id` is None; no insert with NULL.
- [ ] Queries: Remove `pack_id.is_(None)` (and or_ branches) for the three M1 tables in score_resolver, engagement_snapshot_writer, snapshot_writer, score_nightly, outreach_review, briefing, lead_feed (query_service, projection_builder), briefing_views.
- [ ] Optional: Unique constraints on (company_id, as_of, pack_id) for readiness_snapshots and engagement_snapshots if required by plan.
- [ ] Docstrings/comments updated; no “legacy NULL” for M1 tables.
- [ ] Tests: All creations of the three models pass `pack_id`; no NOT NULL failures.

---

## 10. Unrelated Notes

- **company.py** uses `or_()` for search (name / founder_name / notes); not pack-related — no change needed for M1.
- Duplicate Alembic revision files (e.g. `* 2.py`) and “Revision X is present more than once” cause multiple heads and break `alembic upgrade head` in CI/test; should be resolved in a separate cleanup so tests can run.
