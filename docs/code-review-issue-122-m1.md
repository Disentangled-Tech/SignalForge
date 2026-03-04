# Code Review: Issue #122 M1 — Pack-Aware Outreach Schema & Pipeline

**Reviewer:** Maintainer lens (live SaaS)  
**Scope:** M1 only — `OutreachRecommendationResponse`, optional `pack_id`/`workspace_id` in pipeline, `get_or_create_ore_recommendation`, unit tests.

---

## Verdict: **Safe to merge** (after applying the required fix below).

One defect was identified: missing null check after `resolve_pack` could cause `AttributeError` when pack load fails. Fix applied in code; all other checklist items are satisfied.

---

## Checklist

### 1) Backward compatibility

- **Fractional CTO behavior:** Unchanged. When `pack_id` and `workspace_id` are omitted, `_resolve_ore_pack_id` uses `get_default_pack_id(db)`; pipeline logic and upsert key are the same.
- **Renames / defaults:** None. New parameters are optional with no default behavior change for existing callers.

### 2) Pack scoping

- **Enforcement:** Snapshot is filtered by `(company_id, as_of, resolved_pack_id)`; ESL uses `pack_id=resolved_pack_id`; upsert and `get_or_create` use `(company_id, as_of, resolved_pack_id)`. All ORE work is pack-scoped.
- **Cross-tenant:** No new API in M1. When M2 adds `GET /api/outreach/recommendation/{company_id}`, the **route** must restrict `company_id` to the caller’s workspace (e.g. company in workspace). M1 does not introduce tenant leakage; the table is keyed by company/pack, not workspace.

### 3) ESL & safety

- **ESL suppress:** Still forces Observe Only and no draft (unchanged).
- **Playbook sensitivity_levels:** Still cap at Soft Value Share and no draft when entity level not in list (unchanged).
- **Policy gate:** Still uses `pack` (and pack’s `stability_cap_threshold`). No pack config can bypass restrictions.
- **Critic / forbidden_phrases / tone_constraint:** Still applied; no change.

### 4) Pipeline correctness

- **Idempotency:** Upsert by `(company_id, as_of, pack_id)` unchanged. `get_or_create` returns existing row without re-running pipeline — no double scoring or duplicate rows.
- **Race:** Two concurrent `get_or_create` for same key can both run the pipeline; the second will upsert the same row. Result is one row, with possible duplicate work. Acceptable for M1; can be optimized later (e.g. lock or “insert then select”) if needed.

### 5) Data migrations

- **Migrations:** None. No schema or Alembic changes.
- **NOT NULL:** N/A.

### 6) Performance

- **Indexes:** Lookup/upsert use `(company_id, as_of, pack_id)`; unique constraint already supports this. No new indexes required.
- **Joins:** No new joins. `get_or_create` adds one SELECT when the row does not exist; acceptable.

### 7) Tests

- **Coverage:** Explicit `pack_id` same as default; get_or_create (existing / creates / company missing); mapper `ore_recommendation_to_response` with required fields.
- **Gaps:** (1) No test for `workspace_id`-only resolution (e.g. `get_pack_for_workspace` path). (2) No test for `resolve_pack` returning `None` (guard added below makes this behavior explicit). (3) Optional: `generate_ore_recommendation(..., pack_id=other_pack_id)` to assert different playbook/tone (plan M1 “nice to have”).

### 8) Documentation

- No ADR or contract changes. No TODOs left in code.

---

## Top 1 critical issue

1. **Missing null check after `resolve_pack`**  
   `resolve_pack(db, resolved_pack_id)` can return `None` (e.g. pack row missing or `load_pack` failure). The code then calls `get_ore_playbook(pack, ...)` (which tolerates `pack is None`) but later uses `pack.manifest.get("version")` (line ~259), which raises `AttributeError` if `pack is None`.  
   **Fix:** After `pack = resolve_pack(db, resolved_pack_id)`, add:
   ```python
   if pack is None:
       return None
   ```

---

## Required fixes before merge

1. ~~In `app/services/ore/ore_pipeline.py`, after `pack = resolve_pack(db, resolved_pack_id)` (around line 115), add `if pack is None: return None`.~~ **Done** (fix applied).

---

## Suggested follow-ups (non-blocking)

- **Test:** Add a test that `get_or_create_ore_recommendation(..., workspace_id=...)` (no `pack_id`) resolves pack via `get_pack_for_workspace` and returns or creates the correct row.
- **Test:** Add a test that when `resolve_pack` returns `None` (e.g. mock), `generate_ore_recommendation` returns `None` without raising.
- **M2:** When adding the recommendation endpoint, enforce that `company_id` is within the caller’s workspace (or equivalent tenant boundary) so pack resolution by `workspace_id` cannot be abused to see other tenants’ data.
- **Optional:** Consider documenting or testing the concurrent `get_or_create` “double run” behavior; if it becomes a cost concern, add a short comment or follow-up for “lock or insert-then-select” to avoid redundant pipeline runs.

---

## Summary

- **Scope:** M1 only; no scope creep. No new route, no migrations, no change to existing call paths.
- **Behavior:** Default-pack behavior unchanged; new code path only when `pack_id`/`workspace_id` are passed.
- **Security/tenant:** No new API surface in M1; pack and company scoping are correct. M2 must enforce workspace→company access.
- **ESL/safety:** Hard bans and pack-driven gates unchanged.
- **Pipeline:** Idempotent; safe under concurrency (one row, possible duplicate work).
- **Performance:** No new indexes or heavy joins.
- **Tests:** Good coverage; adding `resolve_pack`-returns-`None` and `workspace_id`-only tests would strengthen regression protection.

The null check after `resolve_pack` has been applied; **safe to merge**.
