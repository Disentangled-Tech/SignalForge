# Implementation Plan: Pack-Aware Outreach Recommendation Endpoint (Issue #122)

**Scope:** Refactor Outreach Recommendation API to use pack playbooks, tone constraints, ESL sensitivity gating, and pack scoring breakdown. Add `GET /api/outreach/recommendation/{company_id}` with optional `as_of` and `pack_id`. Endpoint must not contain domain assumptions.

**Constraints:** Live SaaS; backward compatibility and safe migrations over elegance. No breaking DB migrations; staged refactors preferred.

**References:** GitHub [Issue #122](https://github.com/Disentangled-Tech/SignalForge/issues/122), v2-spec.md, CURSOR_PRD.md, TDD_rules.md, SignalForge Architecture Contract, pack_v2_contract.md, ORE design spec.

---

## 1. Current State Assessment

### 1.1 Where Domain Logic Currently Lives

| Area | Location | Notes |
|------|----------|--------|
| **ORE pipeline** | `app/services/ore/ore_pipeline.py` | `generate_ore_recommendation(db, company_id, as_of, …)` — uses default pack only (`get_default_pack_id`), single playbook `DEFAULT_PLAYBOOK_NAME`, ESL from context, policy gate, draft generator, critic, persist to `OutreachRecommendation`. |
| **Playbook loading** | `app/services/ore/playbook_loader.py` | `get_ore_playbook(pack, playbook_name)` — normalizes playbook dict (pattern_frames, value_assets, ctas, forbidden_phrases, sensitivity_levels, tone). Used by pipeline and draft_generator. |
| **Draft generation** | `app/services/ore/draft_generator.py` | `generate_ore_draft(company, recommendation_type, pattern_frame, value_asset, cta, pack=..., explainability_snippet, top_signal_labels, tone_constraint, tone_definition)` — uses `resolve_prompt_content("ore_outreach_v1", pack, ...)`. Pack-aware; no hardcoded founder/startup language in generator. |
| **Policy gate** | `app/services/ore/policy_gate.py` | `check_policy_gate(cooldown_active, stability_modifier, alignment_high, pack)` — pack provides `stability_cap_threshold`. |
| **ESL context** | `app/services/esl/engagement_snapshot_writer.py` | `compute_esl_from_context(db, company_id, as_of, pack_id, core_pack_id)` — returns esl_decision, sensitivity_level, tone_constraint, etc. |
| **Outreach API** | `app/api/outreach.py` | Only `GET /api/outreach/review` — returns weekly review companies (OutreachScore, explain). No per-company recommendation endpoint. |
| **Outreach schemas** | `app/schemas/outreach.py` | `OutreachRecommendationRead` (for ORM), `OutreachReviewItem`, `OutreachReviewResponse`. No response schema for “recommendation kit” (playbook ID, drafts, rationale, sensitivity tag). |
| **Pack resolution** | `app/services/pack_resolver.py` | `get_default_pack_id`, `get_pack_for_workspace(workspace_id)`, `resolve_pack(db, pack_id)`. ORE pipeline uses default pack only. |
| **Weekly review** | `app/services/outreach_review.py` | `get_weekly_review_companies(db, as_of, ..., pack_id=None, workspace_id=None)` — dual-path (lead_feed vs join). Resolves pack via `get_pack_for_workspace` or `get_default_pack_id`. |

**Summary:** ORE domain logic is already largely pack-aware (playbook, tone, sensitivity_levels, forbidden_phrases, policy gate). The gap is: (1) no public API that returns a single company’s recommendation kit; (2) pipeline is invoked only internally (e.g. from tests or future jobs), not from an endpoint; (3) pipeline always uses default pack — no `pack_id` parameter; (4) no formal “LeadScore” or “ESL decision” input abstraction for the endpoint (issue #122 asks for Entity ID, Active pack ID, LeadScore object, ESL decision as input).

### 1.1.1 ESL context return shape (compute_esl_from_context)

`compute_esl_from_context(db, company_id, as_of, pack_id, core_pack_id=None)` returns a dict (or `None` if no ReadinessSnapshot). Typed as `EslContextResult` in `app/services/esl/engagement_snapshot_writer.py`. Consumers (ORE pipeline, `write_engagement_snapshot`) should rely only on these keys:

| Key | Type | Description |
|-----|------|-------------|
| `esl_composite` | float | ESL score (0–1). |
| `stability_modifier` | float | SM component. |
| `recommendation_type` | str | e.g. "Soft Value Share", "Observe Only". |
| `explain` | dict | Explain payload (svi, spi, csi, esl_decision, esl_reason_code, sensitivity_level, tone_constraint, etc.). |
| `cadence_blocked` | bool | True when recent outreach within cooldown. |
| `alignment_high` | bool | From company alignment. |
| `trs` | float | Readiness composite. |
| `pack_id` | UUID or str | Pack used for rubric and policy. |
| `esl_decision` | str | One of: allow, allow_with_constraints, suppress. |
| `esl_reason_code` | str | e.g. "legacy", "blocked_signal". |
| `sensitivity_level` | str or None | From pack/core sensitivity mapping. |
| `signal_ids` | set[str] | **M1 (Issue #120):** Entity’s signal set used for ESL decision. When `core_pack_id` is set, this set comes from **core** SignalInstances; otherwise from **pack** SignalInstances. Used by pack-aware critic (M2/M3). |

Do not rely on undocumented keys. For type-safe access, import `EslContextResult` from `app.services.esl.engagement_snapshot_writer`.

### 1.2 Tight Coupling Areas

- **ore_pipeline ↔ default pack:** Pipeline calls `get_default_pack_id(db)` and `resolve_pack(db, pack_id)`; no way to request another pack without changing callers.
- **outreach_review ↔ workspace/pack:** `get_weekly_review_companies` takes optional `pack_id` and `workspace_id`; used by `GET /api/outreach/review` which does not currently pass pack/workspace from request (relies on internal resolution).
- **Company detail view:** Uses `get_draft_for_company` (BriefingItem.outreach_message), not `OutreachRecommendation`; ORE-generated drafts are not yet exposed on company detail via a dedicated “recommendation” API.
- **Score/ESL data:** Recommendation depends on ReadinessSnapshot + ESL context. ReadinessSnapshot is keyed by (company_id, as_of, pack_id). ESL is computed from context with same pack_id. Tight coupling is appropriate; risk is API layer not passing through pack_id/as_of and defaulting incorrectly.

### 1.3 High-Risk Refactor Zones

- **Changing `generate_ore_recommendation` signature** (e.g. adding required `pack_id`) — all callers must be updated; currently only tests and no HTTP endpoint call it. Low risk if we add optional `pack_id` and keep default-pack behavior.
- **Introducing a “LeadScore” input type** — issue #122 lists “LeadScore object” as input. Today the pipeline derives TRS/ESL from DB (ReadinessSnapshot + compute_esl_from_context). Adding an alternate path that accepts precomputed LeadScore would be a new code path; risk of divergence between “DB path” and “input path.” Prefer: keep single path (load from DB by company_id, as_of, pack_id) and define a **response** schema that exposes “pack scoring breakdown” (TRS, ESL, recommendation_type) rather than a new input schema in the first milestone.
- **Workspace vs pack in API:** `GET /api/outreach/review` does not take workspace_id/pack_id in the issue table. Adding optional `pack_id` (and optionally workspace_id for pack resolution) to the new recommendation endpoint is backward compatible. Resolving pack from workspace when `pack_id` is omitted matches existing patterns (e.g. company detail, briefing).
- **Database:** No schema change required for the new endpoint. `OutreachRecommendation` already has (company_id, as_of, pack_id) and playbook_id, draft_variants, recommendation_type, safeguards_triggered, etc. Optional: ensure we do not add NOT NULL constraints or drop columns in this work.

---

## 2. Proposed Refactor Strategy

### 2.1 Safe Order of Changes

1. **Define response schema and service contract (no breaking changes)**  
   Add `OutreachRecommendationResponse` (and optionally request schema) in `app/schemas/outreach.py`. Add a **service function** that, given (db, company_id, as_of, pack_id), returns either an existing `OutreachRecommendation` or runs the pipeline and returns the result (or None). Keep `generate_ore_recommendation` as-is for now; add a thin wrapper that accepts optional `pack_id` and optional `workspace_id` for pack resolution.

2. **Add optional pack_id (and as_of) to pipeline**  
   Extend `generate_ore_recommendation` to accept optional `pack_id: UUID | None = None` and optional `workspace_id: str | None = None`. When `pack_id` is None, resolve via `get_pack_for_workspace(db, workspace_id)` or `get_default_pack_id(db)`. No change to DB or to existing callers (they don’t pass pack_id).

3. **Implement GET /api/outreach/recommendation/{company_id}**  
   New route: optional query params `as_of`, `pack_id` (and optionally `workspace_id` if multi-workspace). Returns 404 when company or snapshot/recommendation not found. Response body: recommended playbook ID, draft(s), rationale, sensitivity tag (from existing ORM + ESL context). No domain assumptions in the endpoint handler (all logic in service layer).

4. **Ensure playbook eligibility and explainability_template usage**  
   Pipeline already excludes playbooks by sensitivity_level and uses explainability from snapshot; confirm draft uses “explainability_template” from pack/taxonomy if present (e.g. in human_labels or prompt context). Document or add a single place (e.g. playbook or pack prompt_bundles) for “why this outreach approach” if not already covered.

5. **Optional: Support “recommendation without persist”**  
   If product needs a “preview” that does not write to `OutreachRecommendation`, add a parameter to the service to compute and return the kit without upserting. Not required by issue #122 but keeps endpoint flexible.

### 2.2 What to Abstract First

- **Response schema:** `OutreachRecommendationResponse` with: `recommended_playbook_id`, `drafts` (list of draft variants), `rationale` (“Why this outreach approach”), `sensitivity_tag`, and any existing fields from `OutreachRecommendationRead` (e.g. recommendation_type, outreach_score, safeguards_triggered). This gives a stable API contract.
- **Pack resolution at API boundary:** Resolve `pack_id` from query (optional) or from `workspace_id` (optional) so the endpoint is explicitly pack-scoped and workspace-safe when multi_workspace is enabled.

### 2.3 What to Delay

- **LeadScore as input:** Do not add a separate “accept LeadScore object” path in the first milestone. The endpoint can take entity ID + active pack ID + optional as_of; TRS/ESL are loaded from DB (ReadinessSnapshot + compute_esl_from_context). If a future requirement is “recommendation from in-memory LeadScore” (e.g. for preview without snapshot), add a separate service function later.
- **Multiple playbooks per pack:** Issue #122 says “Recommended playbook ID” — pipeline currently uses a single default playbook per run. Keep one playbook per request; multi-playbook selection (e.g. by dimension or rules) can be a later enhancement.
- **Removing legacy outreach paths:** Do not remove or change `get_draft_for_company` (BriefingItem) or existing `GET /api/outreach/review` in this plan. Only add the new endpoint and, if needed, have company detail or briefing optionally consume the new API later.

### 2.4 Temporary Compatibility Layers (If Needed)

- **Default as_of:** When `as_of` is omitted, use latest snapshot date (e.g. same as review: `get_latest_snapshot_date(db)` or today). Document that clients get “latest” recommendation by default.
- **Pack default:** When `pack_id` is omitted, use `get_pack_for_workspace(db, workspace_id)` then `get_default_pack_id(db)` so behavior matches the rest of the app.

---

## 3. File-Level Change Plan

### Step 1: Response schema and service API (no route yet)

| Action | File | Change |
|--------|------|--------|
| Add schema | `app/schemas/outreach.py` | Add `OutreachRecommendationResponse` with: `recommended_playbook_id: str`, `drafts: list[dict]` (or list of a small DraftVariant schema), `rationale: str`, `sensitivity_tag: str | None`, plus fields from existing recommendation (e.g. `recommendation_type`, `outreach_score`, `safeguards_triggered`, `company_id`, `as_of`). Reuse or align with `OutreachRecommendationRead` where appropriate. |
| Optional | `app/schemas/outreach.py` | Add request schema for optional query params (e.g. `as_of: date | None`, `pack_id: UUID | None`) if you want validated query model. |

**New modules:** None.  
**Data migrations:** None.

---

### Step 2: Pipeline accepts optional pack_id and workspace_id

| Action | File | Change |
|--------|------|--------|
| Modify | `app/services/ore/ore_pipeline.py` | Add optional kwargs `pack_id: UUID | None = None`, `workspace_id: str | None = None` to `generate_ore_recommendation`. Resolve pack: if `pack_id` is set use it; else if `workspace_id` is set use `get_pack_for_workspace(db, workspace_id)`; else `get_default_pack_id(db)`. Use resolved pack for playbook, ESL, and persist. |
| Tests | `tests/test_trs_esl_ore_pipeline.py` | Add test: call with explicit `pack_id` (same as default) and assert same result; add test: call with missing company → None; keep existing tests passing. |

**New modules:** None.  
**Data migrations:** None.

---

### Step 3: Service function to get or create recommendation and map to response

| Action | File | Change |
|--------|------|--------|
| Add | `app/services/ore/` (e.g. in `ore_pipeline.py` or new `recommendation_service.py`) | New function: `get_or_create_ore_recommendation(db, company_id, as_of, pack_id=None, workspace_id=None) -> OutreachRecommendation | None`. Internally: resolve pack; load or run `generate_ore_recommendation`; return ORM or None. |
| Add | Same module or `app/schemas/outreach.py` helper | Map `OutreachRecommendation` + optional ESL explain to `OutreachRecommendationResponse` (rationale can be derived from recommendation_type + safeguards_triggered + explain; sensitivity_tag from ESL context or stored in snapshot/explain). |

**New modules:** Optional `app/services/ore/recommendation_service.py` to keep API boundary clear (get_or_create + to_response).  
**Data migrations:** None.

---

### Step 4: GET /api/outreach/recommendation/{company_id}

| Action | File | Change |
|--------|------|--------|
| Add route | `app/api/outreach.py` | `GET /api/outreach/recommendation/{company_id}` with query params: `as_of: date | None = None`, `pack_id: UUID | None = None`, `workspace_id: str | None = None` (optional, for pack resolution when pack_id omitted). Use `get_or_create_ore_recommendation` (or equivalent); if None return 404. Return `OutreachRecommendationResponse`. |
| Register | Already under `prefix="/api/outreach"` in `app/main.py` | No change if router is already included. |
| Auth | `app/api/outreach.py` | Use same auth as review: `Depends(require_auth)`. |

**New modules:** None.  
**Data migrations:** None.

---

### Step 5: Enforce no domain assumptions in endpoint

| Action | File | Change |
|--------|------|--------|
| Review | `app/api/outreach.py` | Ensure no hardcoded “founder”, “startup”, “CTO” in strings or logic. All copy and recommendation type strings come from pack/playbook/ESL. |
| Review | `app/services/ore/draft_generator.py`, `app/services/ore/ore_pipeline.py` | Already use pack/playbook for tone and pattern frames; confirm no leftover domain-specific defaults in fallback or critic. |

---

### Step 6: High-sensitivity and playbook exclusion behavior

| Action | File | Change |
|--------|------|--------|
| Verify | `app/services/ore/ore_pipeline.py` | Already: when `esl_decision == "suppress"` no draft; when playbook `sensitivity_levels` excludes entity’s sensitivity_level, cap at Soft Value Share and no draft. Add or extend test: high-sensitivity signals → no draft (or Observe Only). |
| Tests | `tests/test_trs_esl_ore_pipeline.py` or `tests/test_outreach_api.py` | Test that response for suppressed entity has no drafts and sensitivity_tag set. |

---

### Step 7: Explainability_template in draft generation

| Action | File | Change |
|--------|------|--------|
| Confirm | `app/services/ore/draft_generator.py`, `app/prompts/loader.py` | Draft already receives EXPLAINABILITY_SNIPPET and TOP_SIGNALS from snapshot explain and pack labels. If “explainability_template” in pack taxonomy is a different concept (e.g. per-signal template), ensure it’s used where design spec requires; document in ORE design spec or pack_v2_contract if needed. |
| Optional | Pack playbooks or prompt_bundles | Add “rationale” or “why this approach” template to playbook so response can include a short rationale string. |

---

### Step 8: Code cleanup and documentation

| Action | File | Change |
|--------|------|--------|
| Doc | `docs/Outreach-Recommendation-Engine-ORE-design-spec.md` or `docs/pipeline.md` | Document new endpoint: GET /api/outreach/recommendation/{company_id}, query params, response shape, 404 conditions. |
| Doc | `docs/pack_v2_contract.md` or Architecture Contract | Note that ORE recommendation endpoint is pack-scoped and uses playbook + ESL only (no core changes). |
| Cleanup | `app/api/outreach.py` | Shared helpers (e.g. resolve as_of, resolve pack) if duplicated with review route. |

---

## 4. Regression Risk Analysis

### 4.1 What Could Break

- **Existing callers of `generate_ore_recommendation`:** Only tests. Adding optional params preserves behavior; tests must still pass.
- **GET /api/outreach/review:** Unchanged; no risk if we don’t modify that route.
- **Company detail / briefing:** Unchanged unless we later switch draft source to the new endpoint; out of scope for this plan.
- **Pack resolution when pack_id is None:** Must match current behavior (default pack or workspace’s active pack). If we introduce a bug in resolution order, weekly review or other pack-scoped features could get wrong pack.

### 4.2 How to Detect Breakage

- **Unit tests:** Pipeline tests with and without explicit pack_id; new API test for GET recommendation returns 200 with valid company/snapshot and 404 when company or snapshot missing.
- **Integration tests:** Call GET /api/outreach/recommendation/{company_id} with fixture company that has ReadinessSnapshot + EngagementSnapshot for default pack; assert response has playbook_id, drafts or empty list, rationale, sensitivity_tag.
- **Regression:** Run full test suite (including `test_trs_esl_ore_pipeline`, `test_outreach_review`, and any briefing/company tests). No removal of existing tests.

### 4.3 Tests Required (TDD)

- **Unit:**  
  - Pipeline: `generate_ore_recommendation(..., pack_id=explicit_pack_id)` produces same result as default when explicit_pack_id is default.  
  - Pipeline: `generate_ore_recommendation(..., pack_id=other_pack_id)` uses other pack’s playbook (e.g. different playbook_id or tone).  
  - Schema: `OutreachRecommendationResponse` from ORM + explain has required fields and valid types.

- **API:**  
  - `GET /api/outreach/recommendation/1` with valid company and snapshot → 200, body matches `OutreachRecommendationResponse`.  
  - `GET /api/outreach/recommendation/999999` (no company) → 404.  
  - `GET /api/outreach/recommendation/1?as_of=2020-01-01` with no snapshot for that date → 404.  
  - Optional: `GET /api/outreach/recommendation/1?pack_id=<uuid>` uses that pack; when pack has different playbook, response has different playbook_id or tone.

- **Integration (optional but recommended):**  
  - Fractional CTO pack returns startup-appropriate drafts; bookkeeping pack (if present) returns calm, practical drafts (per issue #122 acceptance criteria).  
  - High-sensitivity entity: response has no drafts (or Observe Only) and sensitivity_tag set.

- **Security/Scoping:**  
  - When multi_workspace_enabled, passing workspace_id does not return another workspace’s data (if endpoint ever filters by workspace; currently recommendation is keyed by company_id, as_of, pack_id).  
  - Auth: unauthenticated request → 401.

---

## 5. Incremental Milestones

| # | Milestone | Deliverables | Can Run in Parallel |
|---|-----------|--------------|----------------------|
| M1 | Schema and pipeline extension | OutreachRecommendationResponse; optional pack_id/workspace_id in generate_ore_recommendation; get_or_create_ore_recommendation service; unit tests | No (foundation) |
| M2 | Recommendation endpoint | GET /api/outreach/recommendation/{company_id} with as_of, pack_id; 404 behavior; API tests | After M1 |
| M3 | Behavior and hardening | High-sensitivity → no draft verified; forbidden_phrases and explainability_template usage confirmed; no domain language in endpoint | After M2 |
| M4 | Code cleanup and documentation | Shared helpers in outreach API; docs (ORE design spec, pipeline, pack_v2_contract); any remaining tests | After M3; can overlap with M3 |

**Parallelism:** M1 must complete first. M2 depends on M1. M3 and M4 can be split across agents: one focuses on tests and behavior (M3), the other on docs and cleanup (M4), after M2 is done.

---

## Summary

- **Current state:** ORE pipeline is pack-aware (playbook, tone, sensitivity, forbidden_phrases); no per-company recommendation API; pipeline uses default pack only.
- **Strategy:** Add optional pack_id/workspace_id to pipeline; introduce response schema and get_or_create service; add GET /api/outreach/recommendation/{company_id} with optional as_of and pack_id; keep all logic in service layer; no DB migrations.
- **Risks:** Regression in pack resolution or in existing ORE tests; mitigated by optional params and TDD.
- **Milestones:** M1 (schema + pipeline + service) → M2 (endpoint) → M3 (behavior/docs) → M4 (cleanup/docs). M3 and M4 can be parallelized after M2.

This plan confines changes to the Core + Pack Architecture boundary (interpretation layer only) and does not modify derivation, core taxonomy, or evidence.
