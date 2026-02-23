You are implementing changes using strict test-driven development (TDD).

Project stack & constraints:
- Backend: FastAPI
- Server-rendered UI: Jinja2 templates (fastapi.templating.Jinja2Templates)
- Frontend: HTML/CSS only (no JS framework, no package.json)
- Inline CSS in app/templates/base.html
- System fonts: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto

Test tooling:
- Runner: pytest (>= 8.0)
- Async: pytest-asyncio (>= 0.24), asyncio_mode = "auto"
- Coverage: pytest-cov (>= 6.0)
- testpaths=["tests"], pythonpath=["."] in pyproject.toml
- Integration marker: @pytest.mark.integration for DB tests
- Run tests: pytest tests/ -v (or make test)

Your job:
1) Write/update tests FIRST (or alongside each small PR step) so failures surface real problems.
2) Tests must cover BOTH:
   a) Most likely user behavior (happy paths)
   b) Edge cases + abuse cases (invalid configs, missing fields, unsafe inputs, multi-tenant leakage)
3) Tests must be written to surface potential problems, not just to pass.
4) Achieve and demonstrate >= 75% code coverage overall, including:
   - Unit tests
   - Regression tests
   - Integration tests (DB) using @pytest.mark.integration
   - UI tests for server-rendered HTML (via FastAPI TestClient + BeautifulSoup)

Non-negotiable rules:
- No “assert True” or trivial tests.
- No tests that simply mirror the implementation line-by-line.
- Assertions must validate: outcomes, side-effects, invariants, and failure modes.
- Every bug fix must include a regression test that fails before the fix.
- Every new or changed module must include tests for error paths.
- Coverage must not decrease in touched modules.

UI testing approach (no JS framework):
- Use FastAPI TestClient to request routes.
- Parse HTML using BeautifulSoup (bs4).
- Assert:
  - Correct elements exist
  - Correct text and labels render
  - Correct links exist
  - Correct badges/flags render
  - Template inheritance is working (base.html applied)
  - “Why you’re seeing this” content matches explainability templates
  - Pack switching UI shows active pack + version + messaging (no auto-reprocess)

Core invariants that MUST have explicit tests:
1) Scoping invariants:
   - All read/write paths for signals/leads require workspace_id AND pack_id.
   - No cross-tenant leakage (tenant A cannot see tenant B).
   - No cross-pack leakage (pack A data cannot appear under pack B).

2) ESL invariants:
   - ESL hard bans are enforced in core, cannot be bypassed by pack config.
   - Blocked/suppressed signals do not surface.
   - allow_with_constraints applies tone constraints correctly.

3) Pipeline invariants:
   - Derivation is idempotent (rerun does not duplicate SignalInstances).
   - Projection updates replace rows (no duplicates in lead_feed).
   - Jobs retry safely (idempotency keys).

4) LLM safety invariants (if drafting is in scope):
   - Raw observation text is NOT passed to the LLM by default.
   - Draft inputs are structured facts (signal_id, explainability, dates, entity metadata).
   - Forbidden phrases are enforced; critic rejects unsafe drafts.

***NEW: Legacy-vs-Pack Parity Harness (mandatory for CTO extraction)***
To ensure we can trust tests and prevent subtle breakage, implement a regression harness that compares outputs from:
- Legacy pipeline (pre-pack behavior)
vs
- Pack pipeline (fractional_cto_v1)

The harness must run the SAME fixed fixture dataset through BOTH and assert:
- Same surfaced entities (set equality)
- Same ordering within tolerance (or same score bands if ordering ties)
- Same LeadCard fields:
  - composite score (exact or within small tolerance if floating decay)
  - top reasons / top signals (same IDs)
  - ESL decision (exact)
  - sensitivity label (exact)
- Same outreach drafts eligibility (same playbook chosen, forbidden phrases absent)

Notes:
- If exact text drafts are non-deterministic, assert draft constraints rather than exact string equality:
  - correct tone class
  - contains required elements (opening/value/CTA)
  - does not contain forbidden phrases
  - references only allowed facts
- This harness must FAIL before the migration changes and PASS after, proving parity.

Test categories (must follow):
A) Unit tests (fast, isolated)
- Pack loader schema validation (missing fields, bad references, invalid semver, invalid sensitivity)
- Regex safety validation (reject too-long patterns; ensure timeouts/guards invoked)
- Deriver rule evaluation (pattern match, thresholds, source scoping)
- Scoring profile application (weights, decay, disqualifiers, thresholds)
- ESL policy evaluation (blocked signals, prohibited combinations, sensitivity mapping)

B) Regression tests (freeze critical behaviors)
- Legacy-vs-Pack Parity Harness for fractional CTO
- Past bug regressions:
  - “test companies not in list” stays fixed
  - “scan all surfaces companies” stays fixed (if applicable)

C) Integration tests (@pytest.mark.integration)
- DB scoping:
  - Insert signals/scores for two workspaces and assert isolation.
  - Insert two packs in same workspace and assert pack isolation.
- Lead feed projection:
  - Verify projection updates on insert and rerun; no duplicates.
- Migration safety:
  - After migration, pack_id fields backfilled and NOT NULL enforced (if applicable).

D) UI tests (server-rendered HTML)
- GET /leads (or equivalent):
  - Renders lead feed with items from lead_feed table
  - Shows sensitivity badge
  - Shows top signals and explainability snippet
- GET /lead/{id}:
  - Shows “Why you’re seeing this” with evidence link
  - Shows outreach draft section and/or generation button state
- Pack selection page/section:
  - Shows active pack + version
  - Shows no-auto-reprocess messaging on switch

Coverage requirements:
- Provide exact commands to run tests and coverage.
- Report coverage before and after changes.
- Coverage must be >= 75% overall.
- Additionally: coverage for newly changed modules must be >= 85% (tighter bar for new code).

Commands:
- Unit+regression: pytest tests/ -v
- Coverage: pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=75
- Integration: pytest tests/ -v -m integration --cov=app --cov-report=term-missing

Output format (strict):
1) Test Plan (what will be tested + why; include risk-based priorities)
2) Test Cases (grouped by Unit/Regression/Integration/UI; include edge cases)
3) Legacy-vs-Pack Parity Harness Design
   - Fixture dataset description
   - What is asserted (fields + tolerances)
   - Determinism strategy (drafts, ordering, timestamps)
4) Tests Added/Updated (file paths + brief description)
5) Fixtures Strategy (what fixtures will be created; how they represent real usage)
6) Commands to Run (tests + coverage; include integration command)
7) Coverage Report (baseline before changes, expected after; include fail-under settings)
8) Confidence Assessment
   - What passing tests guarantee
   - What remains risky or untested and why
   - Follow-up tests to add (if any)

Do NOT start implementing production code until the Test Plan is complete and the first failing tests are written.
If something is hard to test, propose a minimal refactor to make it testable, then test it.