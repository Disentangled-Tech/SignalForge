# SignalForge Developer Onboarding

This document is for developers who need to **maintain, extend, or onboard** onto the SignalForge codebase. It explains what the app does, where things live, how data flows, and how each feature is intended to be used. Use it to jump in without reverse-engineering the repo.

---

## 1. What SignalForge Does (One Paragraph)

SignalForge is a **single-user intelligence assistant** that monitors startup companies and identifies when founders are likely to need technical leadership help (e.g. fractional CTO). It does **not** send outreach automatically—it produces **recommendation kits** (drafts, rationale, safeguards) for human review. The pipeline is: **companies → signals → analysis → scoring → briefing → outreach draft**. Scoring uses **TRS** (Technical Readiness Score) and **ESL** (Engagement Suitability Layer); outreach is produced by the **ORE** (Outreach Recommendation Engine). All outreach behavior is pack-driven and ethically gated (no urgency exploitation, cooldowns, stability caps).

---

## 2. High-Level Architecture

### 2.1 Layers (Bottom → Top)

| Layer | What it is | Key artifacts |
|-------|------------|----------------|
| **Evidence** | Raw citations (web pages, snippets) | Scout: `scout_evidence_bundles`, Evidence Store: `evidence_bundles`, `evidence_sources` |
| **Core Events** | Structured facts from external sources | `SignalEvent` (ingestion adapters, monitor) |
| **Core Signals** | Derived signals from events | `SignalInstance` (core derivers only) |
| **Scoring / ESL** | Pack-weighted interpretation | `ReadinessSnapshot`, `EngagementSnapshot`, `lead_feed` |
| **Outreach** | Human-readable recommendation kits | `OutreachRecommendation` (ORE output) |

### 2.2 Core vs Pack (Critical Boundary)

- **Core** (`app/core_taxonomy/`, `app/core_derivers/`): Canonical `signal_id` taxonomy, **derivers only**. Deterministic, pack-agnostic. Used by the **derive** stage to produce `SignalInstance` rows. Core YAML is validated at app startup.
- **Pack** (`packs/<pack_name>/`): Scoring weights, ESL rubric, playbooks, prompts. Pack-specific interpretation. **Not** used for derivation at runtime—only for scoring, ESL, and ORE. One workspace has one **active pack**; pack selection reloads **analysis config only** (no re-derivation).

See [CORE_VS_PACK_RESPONSIBILITIES.md](CORE_VS_PACK_RESPONSIBILITIES.md) for the full contract.

### 2.3 Workspace and Pack Scoping

- **Workspace**: Tenant boundary. All tenant-visible data (lead feed, briefing, scout runs, outreach) is filtered by `workspace_id`.
- **Pack**: Snapshot and signal data are scoped by `pack_id`. Score, briefing, and ORE resolve pack via `get_pack_for_workspace(db, workspace_id)` (or explicit `pack_id` on internal endpoints).

See [workspace_pack_scoping.md](workspace_pack_scoping.md).

---

## 3. Data Flow Overview

### 3.1 Main Pipeline (Event-Driven): Ingest → Derive → Score

Used for **event-based** signals (funding, job posts, launches, etc.). This is the path that produces pack-scoped TRS/ESL and feeds the briefing and weekly review.

```
External APIs (Crunchbase, Product Hunt, NewsAPI, etc.)
    → run_ingest_daily (normalize, resolve companies, dedupe)
    → signal_events
    → run_deriver (core derivers only; no pack)
    → signal_instances (core pack_id)
    → run_score_nightly (workspace pack: weights + ESL)
    → readiness_snapshots + engagement_snapshots
    → lead_feed (updated incrementally inside run_score_nightly per company)
```

**Lead feed**: `run_score_nightly` updates the `lead_feed` projection **incrementally** as it writes each company’s snapshots (via `upsert_lead_feed_from_snapshots`). A **separate** job `POST /internal/run_update_lead_feed` exists to (re)build the full projection from snapshots (e.g. different `as_of` or backfill) without re-running score.

- **Entry (cron)**: `POST /internal/run_daily_aggregation` (recommended) or individual `run_ingest`, `run_derive`, `run_score`. Optionally `run_update_lead_feed` when you need a full (re)projection only.
- **Idempotency**: Ingest dedupes by `(source, source_event_id)`; derive upserts by `(entity_id, signal_id, pack_id)`; score upserts by `(company_id, as_of, pack_id)`.

### 3.2 Scan Pipeline (Web-Scraping + LLM)

Used for **companies with a website**: discover pages, extract text, store `SignalRecord`, run LLM analysis, deterministic scoring. Updates `company.cto_need_score` and `company.current_stage`.

```
Companies (with website_url)
    → run_scan_all (per company: discover pages, fetch, extract)
    → signal_records (HTML-derived)
    → analyze_company (LLM) → analysis_records
    → score_company (deterministic) → company.cto_need_score, current_stage
```

- **Entry**: `POST /internal/run_scan` or UI "Scan all" on Companies page. Pack is resolved from workspace for analysis attribution.

### 3.3 Scout (Evidence-Only; Separate Flow)

**Does not write to companies, signal_events, or signal_instances.** Produces **Evidence Bundles** only; writes to `scout_runs` and `scout_evidence_bundles`, and optionally to the Evidence Store (`evidence_bundles`, `evidence_sources`).

```
ICP definition + allowlist/denylist
    → Query Planner (families, rotation)
    → Fetch allowed sources (page limit)
    → LLM → EvidenceBundle schema
    → Validation (+ optional verification gate → quarantine on fail)
    → scout_evidence_bundles (+ Evidence Store when enabled)
```

- **Entry**: `POST /internal/run_scout` (internal token) or UI: GET `/scout`, GET `/scout/new`, GET `/scout/runs/{run_id}`, POST `/scout/runs`.

### 3.4 Diff-Based Monitor (Separate Flow)

When implemented: fetches company pages, diffs vs previous snapshots, LLM interpretation → **SignalEvent** rows with `source="page_monitor"`. Those events then flow through **derive** and **score** like any other ingested events. No pack in snapshot/diff logic.

- **Entry**: `POST /internal/run_monitor`.

### 3.5 Briefing and Outreach

- **Briefing**: Selects top companies (from `lead_feed` when populated, else join of ReadinessSnapshot + EngagementSnapshot), generates briefing items, optional email. Uses both Scan path (analysis records) and event path (snapshots).
- **ORE (Outreach Recommendation Engine)**: For each company in weekly review: policy gate → strategy selector (deterministic) → draft generator (LLM) → critic → optional polish → persist `OutreachRecommendation`. All wording and strategy come from pack/playbook. No auto-send.

---

## 4. Where Everything Lives

### 4.1 Application Entry and Routing

| What | Where | Notes |
|------|--------|--------|
| App creation, lifespan, health | `app/main.py` | Startup validates core taxonomy + derivers; DB check. |
| API route registration | `app/main.py` | Auth, briefing, companies, outreach, watchlist, views, internal. |
| Internal job endpoints | `app/api/internal.py` | POST: run_scan, run_briefing, run_score, run_alert_scan, run_derive, run_ingest, run_update_lead_feed, run_backfill_lead_feed, run_daily_aggregation, run_watchlist_seed, run_monitor, run_scout, run_bias_audit, evidence/store. GET: scout_analytics, scout_runs, evidence/bundles, evidence/quarantine, evidence/quarantine/{quarantine_id}. All require `X-Internal-Token`. |

### 4.2 API and Views

| Area | Routes / location | Purpose |
|------|-------------------|--------|
| **Auth** | `app/api/auth.py` | Login, logout, `/api/auth/me`. |
| **Companies** | `app/api/companies.py` | CRUD, list, top, bulk import. |
| **Briefing** | `app/api/briefing.py`, `app/api/briefing_views.py` | API daily briefing; HTML views for briefing by date, generate. |
| **Outreach** | `app/api/outreach.py` | `GET /api/outreach/review`, `GET /api/outreach/recommendation/{company_id}`. |
| **Watchlist** | `app/api/watchlist.py` | POST (add), DELETE `/{company_id}` (remove), GET (list). |
| **Scout (UI)** | `app/api/scout_views.py` | GET `/scout`, GET `/scout/new`, GET `/scout/runs/{run_id}`, POST `/scout/runs` (session auth, workspace-scoped). |
| **Settings** | `app/api/settings_views.py` | Settings page, profile, run ingest from UI. |
| **Bias** | `app/api/bias_views.py` | Bias reports list/detail, run audit. |
| **Views (HTML)** | `app/api/views.py` | `/`, `/login`, `/companies`, company detail, scan, outreach CRUD, etc. |

### 4.3 Pipeline and Stages

| What | Where | Purpose |
|------|--------|--------|
| Stage protocol and registry | `app/pipeline/stages.py` | `STAGE_REGISTRY`: ingest, derive, score, update_lead_feed, daily_aggregation, watchlist_seed. |
| Deriver execution | `app/pipeline/deriver_engine.py` | Reads core derivers, writes core `SignalInstance`s. |
| Daily aggregation | `app/services/aggregation/daily_aggregation.py` | Orchestrates ingest → derive → score; returns ranked companies. |
| Lead feed update | `app/services/lead_feed/run_update.py` | Builds `lead_feed` from snapshots. |

### 4.4 Ingestion

| What | Where | Purpose |
|------|--------|--------|
| Daily ingest orchestrator | `app/services/ingestion/ingest_daily.py` | Picks adapters from env, calls `run_ingest`. |
| Core ingest logic | `app/ingestion/ingest.py` | Normalize, resolve companies, store events (dedupe). |
| Normalization | `app/ingestion/normalize.py` | Event type validation (core/pack). |
| Adapters | `app/ingestion/adapters/` | Crunchbase, Product Hunt, NewsAPI, GitHub, Delaware Socrata, TestAdapter. |

### 4.5 Core Taxonomy and Derivers

| What | Where | Purpose |
|------|--------|--------|
| Canonical signal_ids, dimensions | `app/core_taxonomy/taxonomy.yaml`, `app/core_taxonomy/loader.py` | Single source of truth for signal IDs and M/C/P/G. |
| Core derivers (passthrough + pattern) | `app/core_derivers/derivers.yaml`, `app/core_derivers/loader.py` | Used by derive only; validated at startup. |
| Deriver engine | `app/pipeline/deriver_engine.py` | Reads `SignalEvent`, writes core `SignalInstance` with `evidence_event_ids`. |

### 4.6 Scoring and ESL

| What | Where | Purpose |
|------|--------|--------|
| Readiness (TRS) | `app/services/readiness/readiness_engine.py`, `snapshot_writer.py`, `score_nightly.py` | Weights from pack; reads core instances (via event resolver). |
| ESL | `app/services/esl/esl_engine.py`, `engagement_snapshot_writer.py` | BE×SM×CM×AM; stability cap; recommendation type. |
| Event → snapshot data | `app/services/readiness/event_resolver.py` | Resolves events from core SignalInstances for scoring. |

### 4.7 ORE (Outreach Recommendation Engine)

| What | Where | Purpose |
|------|--------|--------|
| Pipeline | `app/services/ore/ore_pipeline.py` | TRS → ESL → policy gate → strategy → draft → critic → persist. |
| Policy gate | `app/services/ore/policy_gate.py` | Cooldown, stability cap, alignment. |
| Strategy selector | `app/services/ore/strategy_selector.py` | Deterministic: channel, CTA, value asset, pattern frame by dominant dimension. |
| Draft generator | `app/services/ore/draft_generator.py` | LLM draft from playbook. |
| Critic / polish | `app/services/ore/critic.py`, `polisher.py` | Safety and tone checks; optional ORE polish. |
| Playbook loading | `app/services/ore/playbook_loader.py` | Load playbook by name from pack. |

### 4.8 Scan (Web-Scraping Path)

| What | Where | Purpose |
|------|--------|--------|
| Orchestrator | `app/services/scan_orchestrator.py` | Per-company: discover pages, fetch, store signals, analyze, score. |
| Page discovery | `app/services/page_discovery.py` | Discovers blog, jobs, careers, etc. from company URL. |
| Fetcher | `app/services/fetcher.py` | Fetch HTML. |
| HTML→text extractor | `app/services/extractor.py` | `extract_text` (shared by scan, Scout, monitor). `app/extractor/service.py` is Evidence Bundle→core event extraction (Scout/verification), not HTML. |
| Analysis / scoring | `app/services/analysis.py`, `app/services/scoring.py` | LLM analysis → AnalysisRecord; deterministic score → company. |
| Signal storage (scan) | `app/services/signal_storage.py` | Store `SignalRecord` from scan. |

### 4.9 Scout (Discovery)

| What | Where | Purpose |
|------|--------|--------|
| Scout service | `app/services/scout/discovery_scout_service.py` | Query plan → fetch → LLM → validate → persist bundles. |
| Query planner | `app/scout/query_planner.py`, `app/scout/query_families.py` | Diversified queries from ICP + rubric; families/rotation. |
| Sources | `app/scout/sources.py` | Allowlist/denylist filtering. |
| Evidence Store (write) | `app/evidence/store.py` | Persist evidence bundles, sources, claims; quarantine. |
| Evidence Repository (read) | `app/evidence/repository.py` | Read-only access to stored evidence. |

### 4.10 Briefing and Lead Feed

| What | Where | Purpose |
|------|--------|--------|
| Briefing service | `app/services/briefing.py` | select_top_companies, get_emerging_companies, generate_briefing. |
| Lead feed projection | `app/services/lead_feed/projection_builder.py`, `query_service.py` | Build and query lead_feed from snapshots. |
| Outreach review | `app/services/outreach_review.py` | Top companies for weekly review (outreach score). |

### 4.11 Packs and Config

| What | Where | Purpose |
|------|--------|--------|
| Pack loader | `app/packs/loader.py` | Load pack from disk; resolve_pack for analysis config only. |
| Pack resolver | `app/services/pack_resolver.py` | get_default_pack_id, get_pack_for_workspace. |
| Pack config dirs | `packs/fractional_cto_v1/`, `packs/example_v2/` | v1 full config; v2 minimal (scoring, ESL, playbooks). |

### 4.12 Data Layer

| What | Where | Purpose |
|------|--------|--------|
| DB session | `app/db/session.py` | Engine, SessionLocal, get_db. |
| ORM models | `app/models/` | One file per model (Company, SignalEvent, SignalInstance, ReadinessSnapshot, EngagementSnapshot, OutreachRecommendation, etc.). |
| Pydantic schemas | `app/schemas/` | API request/response and canonical read schemas. |

### 4.13 LLM and Prompts

| What | Where | Purpose |
|------|--------|--------|
| LLM abstraction | `app/llm/` | Provider interface; Anthropic-only (ADR-012). |
| Prompts | `app/prompts/` | Versioned by filename; loader in `app/prompts/loader.py`. |

### 4.14 Monitor (Diff-Based)

| What | Where | Purpose |
|------|--------|--------|
| Runner | `app/monitor/runner.py` | Orchestrate fetch → diff → interpret. |
| Detector / snapshot store | `app/monitor/detector.py`, `snapshot_store.py` | Page diff detection; store snapshots. |
| Interpretation | `app/monitor/interpretation.py` | LLM interpretation to core event candidates. |

---

## 5. Features: How They’re Used and Where They Live

### 5.1 Companies

- **Intent**: Manage the set of companies to monitor (add, edit, delete, bulk import). Company is the main entity; scoring and outreach are per-company.
- **Entry points**: UI `/companies`, add/import forms, company detail; API `GET /api/companies`, `GET /api/companies/{id}`, `POST /api/companies` (create), `POST /api/companies/import` (bulk).
- **Location**: `app/api/companies.py`, `app/api/views.py` (companies list/detail/edit/delete/scan), `app/services/company.py`, `app/models/company.py`.
- **Data**: `companies` table; optional `website_url` for scan path; `cto_need_score`/`current_stage` denormalized from scan path (default pack).

### 5.2 Ingestion (Event-Driven Signals)

- **Intent**: Pull events from external APIs (funding, job posts, launches), normalize, resolve to companies, store as `SignalEvent`. Dedupe by `(source, source_event_id)`.
- **Entry points**: `POST /internal/run_ingest` or as first step of `POST /internal/run_daily_aggregation`. Optional `workspace_id`, `pack_id` for job attribution.
- **Location**: `app/services/ingestion/ingest_daily.py`, `app/ingestion/ingest.py`, `app/ingestion/adapters/`.
- **Data flow**: Adapters → raw events → normalize (event type validation) → resolve_or_create_company → insert `signal_events`.

### 5.3 Derive (Events → Core Signals)

- **Intent**: Turn `SignalEvent` rows into `SignalInstance` rows using **core derivers only** (passthrough + pattern). Pack-agnostic; writes to core pack_id.
- **Entry points**: `POST /internal/run_derive` or second step of daily aggregation. Does not require a pack for execution.
- **Location**: `app/pipeline/deriver_engine.py`, `app/core_derivers/`.
- **Data flow**: Read SignalEvents (with company_id) → apply core derivers → upsert SignalInstance by `(entity_id, signal_id, pack_id)` with core pack; store `evidence_event_ids`.

### 5.4 Score (TRS + ESL)

- **Intent**: Compute TRS and ESL from core SignalInstances using the **workspace’s active pack** (weights, ESL rubric only). Write pack-scoped ReadinessSnapshot and EngagementSnapshot.
- **Entry points**: `POST /internal/run_score` or third step of daily aggregation. Optional `workspace_id`, `pack_id`; pack defaults to workspace active pack.
- **Location**: `app/services/readiness/score_nightly.py`, `readiness_engine.py`, `snapshot_writer.py`, `app/services/esl/`.
- **Data flow**: For each company, event_resolver loads event-like data from core instances → readiness engine (pack weights) → engagement snapshot writer (ESL) → upsert snapshots by `(company_id, as_of, pack_id)`.

### 5.5 Lead Feed

- **Intent**: Projection table for fast briefing and weekly review; avoids heavy joins when populated.
- **Entry points**: Updated **inside** `run_score_nightly` (incrementally per company via `upsert_lead_feed_from_snapshots`). Separately, `POST /internal/run_update_lead_feed` (re)builds the full projection from snapshots for workspace/pack/as_of without re-scoring. Optional `workspace_id`, `pack_id`, `as_of`.
- **Location**: `app/services/lead_feed/run_update.py`, `projection_builder.py` (includes `upsert_lead_feed_from_snapshots`), `query_service.py`.
- **Data flow**: During score: for each company, after writing ReadinessSnapshot + EngagementSnapshot, `upsert_lead_feed_from_snapshots` upserts that row into `lead_feed`. Standalone `run_update_lead_feed` calls `build_lead_feed_from_snapshots` to (re)project from snapshots. When lead_feed has rows, briefing and review prefer it.

### 5.6 Scan (Website-Based Path)

- **Intent**: For companies with `website_url`: discover pages, fetch HTML, extract text, store as `SignalRecord`; run LLM analysis and deterministic scoring; update `company.cto_need_score` and `current_stage`.
- **Entry points**: `POST /internal/run_scan` or UI "Scan all" / per-company rescan. Workspace optional for pack.
- **Location**: `app/services/scan_orchestrator.py`, `app/services/page_discovery.py`, `app/services/analysis.py`, `app/services/scoring.py`, `app/services/signal_storage.py`.
- **Data flow**: Companies with website → discover pages → fetch → extract → SignalRecord → analyze_company (LLM) → AnalysisRecord → score_company → company fields.

### 5.7 Briefing

- **Intent**: Select top companies (from lead_feed or snapshot join), generate briefing items (LLM), optionally send email.
- **Entry points**: `POST /internal/run_briefing` or UI briefing page “Generate”. Optional `workspace_id`.
- **Location**: `app/services/briefing.py`, `app/api/briefing.py`, `app/api/briefing_views.py`.
- **Data flow**: `generate_briefing` uses `select_top_companies` (not `get_emerging_companies`). Then for each company: LLM briefing entry, `generate_outreach`, persist BriefingItem; optional send_briefing_email. `get_emerging_companies` is used for the ranked list and weekly review.

### 5.8 Outreach Review and ORE

- **Intent**: Surface top companies by OutreachScore for weekly review; per company, return ORE kit (recommendation type, channel, drafts, rationale, safeguards). No auto-send.
- **Entry points**: `GET /api/outreach/review` (list); `GET /api/outreach/recommendation/{company_id}` (kit). Pack/workspace resolved via query params or session.
- **Location**: `app/api/outreach.py`, `app/services/outreach_review.py`, `app/services/ore/ore_pipeline.py` (and rest of `app/services/ore/`).
- **Data flow**: review: ranked companies from snapshots/lead_feed. Recommendation: load snapshot + ESL context → policy gate → strategy selector → draft generator → critic → optional polish → upsert OutreachRecommendation by (company_id, as_of, pack_id).

### 5.9 Scout (Discovery, Evidence-Only)

- **Intent**: LLM-powered discovery: ICP + allowlist/denylist → queries → fetch → LLM → Evidence Bundles. No company or signal writes; only scout tables and optional Evidence Store.
- **Entry points**: `POST /internal/run_scout` (token); UI GET `/scout`, GET `/scout/runs/{id}`, POST `/scout/runs` (session, workspace-scoped).
- **Location**: `app/services/scout/discovery_scout_service.py`, `app/scout/query_planner.py`, `app/evidence/store.py`, `app/api/scout_views.py`.
- **Data flow**: Plan queries → fetch allowed URLs → LLM → validate EvidenceBundle → optional verification → persist scout_evidence_bundles + evidence_bundles/sources if store enabled.

### 5.10 Watchlist

- **Intent**: Let user mark companies for follow-up; list watchlist for the workspace.
- **Entry points**: `POST /api/watchlist` (add), `DELETE /api/watchlist/{company_id}` (remove), `GET /api/watchlist` (list). UI may surface watchlist on company or briefing.
- **Location**: `app/api/watchlist.py`, `app/models/watchlist.py`.

### 5.11 Watchlist Seeder

- **Intent**: Seed companies from Scout evidence bundles (e.g. create companies from candidate names/websites in bundles).
- **Entry points**: `POST /internal/run_watchlist_seed` with body (e.g. run_id, workspace_id). Token auth.
- **Location**: `app/services/watchlist_seeder/run_seed.py`, `app/api/internal.py`.

### 5.12 Bias Audit

- **Intent**: Monthly bias check for demographic skew; produces bias reports.
- **Entry points**: `POST /internal/run_bias_audit` or UI bias reports “Run”.
- **Location**: `app/services/bias_audit.py`, `app/api/bias_views.py`, `app/api/internal.py`.

### 5.13 Monitor (Diff-Based)

- **Intent**: Detect page changes on company URLs, interpret via LLM, emit SignalEvent with `source="page_monitor"` for derive/score.
- **Entry points**: `POST /internal/run_monitor` (when implemented). Optional workspace_id, company_ids.
- **Location**: `app/monitor/runner.py`, `app/monitor/detector.py`, `app/monitor/interpretation.py`.

---

## 6. Key Concepts (Quick Reference)

| Concept | Meaning |
|--------|---------|
| **TRS** | Technical Readiness Score (0–100). Dimensions: Momentum (M), Complexity (C), Pressure (P), Leadership Gap (G). |
| **ESL** | Engagement Suitability Layer. Formula: BE × SM × CM × AM. Modulates outreach timing; caps and cooldowns protect founders. |
| **ORE** | Outreach Recommendation Engine. Produces recommendation type, channel, draft variants, rationale, safeguards. Pack/playbook-driven. |
| **OutreachScore** | TRS × ESL–derived score used for ranking and gating. |
| **Core vs pack** | Core = taxonomy + derivers (pack-agnostic). Pack = scoring, ESL, playbooks, prompts (analysis config only at runtime). |
| **Workspace** | Tenant boundary; all tenant-visible data scoped by workspace_id. |
| **Active pack** | Pack assigned to a workspace; used for score, briefing, ORE. Changing it reloads analysis config only. |
| **Lead feed** | Projection table from snapshots for fast briefing/review; optional but preferred when populated. |

See [GLOSSARY.md](GLOSSARY.md) for full acronyms and terms.

---

## 7. Development Workflow

### 7.1 First-Time Setup

```bash
./scripts/setup.sh --dev --start
# or: make install && cp .env.example .env && createdb signalforge_dev && alembic upgrade head && make dev
```

- Server: `http://localhost:8000`. Use `signalforge_dev` for daily work; tests use `signalforge_test`.
- Required env: `DATABASE_URL`, `SECRET_KEY`, `INTERNAL_JOB_TOKEN`, `LLM_PROVIDER=anthropic`, `LLM_API_KEY` (or `ANTHROPIC_API_KEY`). See `.env.example` and [CLAUDE.md](../CLAUDE.md).

### 7.2 Common Commands

| Command | Purpose |
|---------|---------|
| `make dev` | Start dev server (auto-reload). |
| `make test` | Run full test suite. |
| `make lint` | Ruff check. |
| `make migrate` | Create new Alembic migration. |
| `make upgrade` | Apply migrations. |
| `make signals-daily` | Run daily aggregation (ingest → derive → score) via script. |

### 7.3 Testing

- `pytest tests/ -v` — all tests. Use `-k "readiness"` or `-m "not integration"` to narrow. Serial: `-p no:xdist` to avoid DB contention.
- Fixtures: `db` (Session), `client` (TestClient). See `tests/conftest.py`.
- TDD: write tests first; see [rules/TDD_rules.md](../rules/TDD_rules.md).

### 7.4 Where to Add New Behavior

| If you want to… | Add or change… |
|------------------|-----------------|
| New event source | New adapter in `app/ingestion/adapters/`, register in `ingest_daily._get_adapters()`. |
| New signal type (event → signal) | Core taxonomy + core deriver entry (passthrough or pattern). |
| New scoring dimension or weight | Pack `scoring.yaml` / `analysis_weights.yaml` (and pack loader if new shape). |
| New ESL rule or cap | Pack `esl_policy.yaml` / `esl_rubric.yaml` and ESL engine. |
| New outreach strategy or copy | Pack playbooks and optional prompt_bundles; ORE uses playbook. |
| New API endpoint | New or existing router in `app/api/`; register in `main.py`. |
| New internal job | New handler in `app/api/internal.py`; optionally add to daily aggregation if it’s a stage. |

---

## 8. Security and Ethics

- **Internal endpoints**: All `/internal/*` endpoints (GET and POST) require `X-Internal-Token` (constant-time comparison). Used for cron/scripts and internal tooling only.
- **No automatic outreach**: ORE produces drafts and rationale; human always reviews before any send.
- **ESL guardrails**: Stability cap (SM < 0.7 → max Soft Value Share), cooldown (CM), no urgency exploitation. See [CLAUDE.md](../CLAUDE.md) “Ethical Design Guardrails.”
- **Core hard bans**: Certain signal_ids are never allowed to drive outreach; see `CORE_BAN_SIGNAL_IDS` and [CORE_BAN_SIGNAL_IDS.md](CORE_BAN_SIGNAL_IDS.md).
- **Bias auditing**: Bias audit job and reports; no neurodivergence inference.

---

## 9. Pointers to Deeper Docs

| Topic | Document |
|-------|----------|
| Pipeline stages, endpoints, Scan vs Ingest | [pipeline.md](pipeline.md) |
| Signal and snapshot schemas, pack-scoping | [signal-models.md](signal-models.md) |
| Core vs pack, derive/score contract | [CORE_VS_PACK_RESPONSIBILITIES.md](CORE_VS_PACK_RESPONSIBILITIES.md) |
| Deriver types, schema, evidence | [deriver-engine.md](deriver-engine.md) |
| Scout flow, evidence-only | [discovery_scout.md](discovery_scout.md) |
| Evidence Store schema, quarantine | [evidence-store.md](evidence-store.md) |
| ORE design, policy gate, strategy | [Outreach-Recommendation-Engine-ORE-design-spec.md](Outreach-Recommendation-Engine-ORE-design-spec.md) |
| Workspace and pack scoping | [workspace_pack_scoping.md](workspace_pack_scoping.md) |
| Ingestion adapters, env vars | [ingestion-adapters.md](ingestion-adapters.md) |
| Acronyms and terms | [GLOSSARY.md](GLOSSARY.md) |
| ADRs | In `rules/` (e.g. ADR-010–013) and `docs/` (e.g. ADR-001); see [GLOSSARY.md](GLOSSARY.md) ADR Quick Reference. |
| TDD | [rules/TDD_rules.md](../rules/TDD_rules.md) |
| Quick reference for AI/editor | [CLAUDE.md](../CLAUDE.md) |

Use this onboarding doc to orient yourself; use the linked docs and code when you need details on a specific feature or contract.
