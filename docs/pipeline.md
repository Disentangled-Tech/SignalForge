# Pipeline Stages

Stages are invoked via `/internal/*` endpoints (cron or scripts). Each stage is workspace- and pack-scoped.

| Stage | Endpoint | Description | Idempotency |
|-------|----------|-------------|-------------|
| **ingest** | `POST /internal/run_ingest` | Fetch raw events, normalize, resolve companies, store `signal_events` | Dedup by `(source, source_event_id)` |
| **derive** | `POST /internal/run_derive` | Populate `signal_instances` from `SignalEvents` using **core derivers only** (pack-independent; writes to core pack) | Upsert by `(entity_id, signal_id, pack_id)` |
| **score** | `POST /internal/run_score` | Compute TRS + ESL using workspace pack **analysis config only** (weights, ESL); company eligibility for scoring is not narrowed by pack (Issue #290) | Upsert by `(company_id, as_of, pack_id)` |
| **update_lead_feed** | `POST /internal/run_update_lead_feed` | Project `lead_feed` from snapshots | Upsert by `(workspace_id, entity_id, pack_id)` |

## Pack selection

Changing a workspace's **active pack** only reloads **analysis config** (scoring, ESL, playbooks, prompts). It does not re-run derivation or change ingestion scope; the set of companies eligible for scoring is pack-invariant when the core pack is installed. For definitions and the full contract, see [GLOSSARY](GLOSSARY.md) (**Active pack**, **Pack selection**) and [ADR-003](ADR-001-Introduce-Declarative-Signal-Pack-Architecture.md) (No Automatic Reprocessing on Pack Switch).

## API Behavior

### POST /internal/run_score

- **Optional query params** (Phase 3):
  - `workspace_id` (UUID): Workspace to score for. When omitted, uses default workspace.
  - `pack_id` (UUID): Pack to use for scoring. When omitted, uses workspace's `active_pack_id`; falls back to default pack when workspace has none.
- **Validation**: Invalid UUIDs for `workspace_id` or `pack_id` return **422 Unprocessable Entity** with detail `"Invalid {param}: must be a valid UUID"`.
- **Pack resolution**: When `pack_id` omitted, `get_pack_for_workspace(db, workspace_id)` resolves the pack. Ensures workspace-specific pack selection for multi-tenant readiness.
- **Issue #287 (M3)**: Score reads from core SignalInstances (via evidence events); applies the workspace pack for weights and ESL rubric; writes pack-scoped ReadinessSnapshot and EngagementSnapshot.

### POST /internal/run_derive

- **Does not require a pack** (Issue #287 M2): Derive runs without a pack. It uses core derivers only and writes to core signal instances (core pack sentinel). When `pack_id` is omitted, the stage runs with no workspace pack; when provided, it is used for JobRun audit only. If the core pack is not installed (migration `20260226_core_pack_sentinel`), the endpoint returns **200** with `status: "skipped"` and an error message. No 400 for missing pack.
- **Post-deploy (Issue #287)**: After deploying the core-pack refactor, **run derive** (e.g. once or on the next nightly) so core signal instances exist. Score reads from core instances; until derive has run, companies that only had pre-deploy (pack-scoped) instances may have no readiness snapshot unless the snapshot writer fallback (pack-scoped events) applies. The daily aggregation job (ingest → derive → score) ensures correct order.
- **ORE pipeline**: Outreach recommendation generation uses the legacy ESL path (pack-scoped signal set) and does not pass `core_pack_id` (Issue #287).

### POST /internal/run_update_lead_feed

- **Optional query params** (Phase 1, Issue #225):
  - `workspace_id` (UUID): Workspace to project for. When omitted, uses default workspace.
  - `pack_id` (UUID): Pack to use. When omitted, uses workspace's `active_pack_id`; falls back to default pack.
  - `as_of` (date, YYYY-MM-DD): Snapshot date. Default: today.
- **Validation**: Invalid UUIDs for `workspace_id` or `pack_id` return **422 Unprocessable Entity**.
- **Pack resolution**: Same as run_score/run_derive. Writes only to `(workspace_id, pack_id, entity_id)`; no cross-tenant leakage.
- **Issue #287 M5**: When the core pack is installed, `last_seen` on lead_feed rows is taken from core SignalInstances; projection key remains `(workspace_id, pack_id)`.

## Ingestion Adapters

Adapters fetch raw events from external sources. `run_ingest_daily` uses adapters returned by `_get_adapters()` based on environment variables.

| Adapter | Env vars | Event types | Notes |
|---------|----------|-------------|-------|
| **Crunchbase** | `CRUNCHBASE_API_KEY`, `INGEST_CRUNCHBASE_ENABLED=1` | funding_raised | Requires Crunchbase API license. See [data.crunchbase.com/docs](https://data.crunchbase.com/docs). |
| **Product Hunt** | `PRODUCTHUNT_API_TOKEN`, `INGEST_PRODUCTHUNT_ENABLED=1` | launch_major | GraphQL API. Rate limits apply. See [api.producthunt.com/v2/docs](https://api.producthunt.com/v2/docs). |
| **NewsAPI** | `NEWSAPI_API_KEY`, `INGEST_NEWSAPI_ENABLED=1` | funding_raised | Keyword-based queries. 100 req/day free tier. See [ingestion-adapters.md](ingestion-adapters.md#newsapi). |
| **TestAdapter** | `INGEST_USE_TEST_ADAPTER=1` | funding_raised, job_posted_engineering, cto_role_posted | Tests only. When set, only TestAdapter is used. |

When `INGEST_USE_TEST_ADAPTER=1`, only TestAdapter is returned. Otherwise, Crunchbase is included when both `INGEST_CRUNCHBASE_ENABLED=1` and `CRUNCHBASE_API_KEY` are set; Product Hunt when both `INGEST_PRODUCTHUNT_ENABLED=1` and `PRODUCTHUNT_API_TOKEN` are set; NewsAPI when both `INGEST_NEWSAPI_ENABLED=1` and `NEWSAPI_API_KEY` are set.

For detailed setup, API key acquisition, rate limits, and pagination, see [ingestion-adapters.md](ingestion-adapters.md).

## Daily Aggregation Job (Issue #246)

The **daily aggregation job** is the recommended entry point for cron. It runs ingest → derive → score in a single call, ensuring correct stage order and returning a ranked list of emerging companies.

### Flow

| Step | Stage | Action |
|------|-------|--------|
| 1 | Ingest | `run_ingest_daily` — fetch events, normalize, resolve companies, store `signal_events` |
| 2 | Derive | `run_deriver` — populate `signal_instances` from `SignalEvents` |
| 3 | Score | `run_score_nightly` — compute TRS + ESL, write snapshots, update lead_feed |
| 4 | Output | Ranked companies via `get_emerging_companies` (or `get_emerging_companies_from_feed`) |

### Endpoint

- **`POST /internal/run_daily_aggregation`**
  - **Auth**: `X-Internal-Token` header required.
  - **Idempotency**: `X-Idempotency-Key` header (optional). Use workspace-scoped keys (e.g. `{workspace_id}:{date}`).
  - **Query params**: `workspace_id`, `pack_id` (optional; same resolution as other stages).
  - **Response**: `status`, `job_run_id`, `inserted`, `companies_scored`, `ranked_count`, `error`.

### Cron Recommendation

- **Option A (recommended)**: Call `POST /internal/run_daily_aggregation` once per day.
- **Option B (granular)**: `POST /internal/run_ingest` (hourly) + `POST /internal/run_derive` + `POST /internal/run_score` (daily).

Option A simplifies operations and ensures correct stage order.

### Environment Variables

Same as individual stages. See [ingestion-adapters.md](ingestion-adapters.md) for adapter-specific vars:

- `INGEST_USE_TEST_ADAPTER=1` — tests only; uses TestAdapter only.
- `CRUNCHBASE_API_KEY`, `INGEST_CRUNCHBASE_ENABLED=1` — Crunchbase.
- `PRODUCTHUNT_API_TOKEN`, `INGEST_PRODUCTHUNT_ENABLED=1` — Product Hunt.
- `NEWSAPI_API_KEY`, `INGEST_NEWSAPI_ENABLED=1` — NewsAPI.
- `INTERNAL_JOB_TOKEN` — required for all `/internal/*` endpoints.

### CLI

```bash
make signals-daily
# or
uv run python scripts/run_daily_aggregation.py
```

## Scan vs Ingest/Derive/Score

Two pipelines feed the fractional CTO use case; they use different data models and entry points.

| Pipeline | Entry | Data model | Output |
|----------|-------|------------|--------|
| **Scan** | `POST /internal/run_scan` or Companies page "Scan all" | Web scraping → `SignalRecord` (HTML-derived) | `AnalysisRecord` → `company.cto_need_score` via `score_company` |
| **Ingest → Derive → Score** | `POST /internal/run_ingest`, `run_derive`, `run_score` | Events → `SignalEvent` → `SignalInstance` (event-derived) | `ReadinessSnapshot` + `EngagementSnapshot` |

**Relationship**

- **Scan**: For companies with `website_url`. Discovers pages, extracts text, stores `SignalRecord`. Runs LLM analysis (stage, pain signals) and deterministic scoring. Updates `company.cto_need_score` and `company.current_stage`. Pack is resolved via `get_default_pack(db)` and passed to `analyze_company` / `score_company`.
- **Ingest/Derive/Score**: For event-driven signals (e.g. funding, job posts). Normalizes events into `SignalEvent`, derives `SignalInstance` via **core derivers only** (pack-independent), computes TRS + ESL using workspace pack analysis config, writes pack-scoped snapshots. Workspace-scoped when multi-tenant (Issue #290).
- **Briefing**: Uses both. `select_top_companies` (legacy) and `get_emerging_companies` (pack) can surface companies. Pack path reads from `lead_feed` when populated, else join of ReadinessSnapshot + EngagementSnapshot.
- **Discovery Scout**: Separate flow (not in the table above). LLM discovery produces Evidence Bundles only; no signals, no entity writes. See [discovery_scout.md](discovery_scout.md).

## Phase 4: Briefing and Weekly Review Dual-Path (Issue #225)

When `lead_feed` has rows for workspace/pack/as_of, the briefing page and weekly review
prefer reading from the projection instead of joining ReadinessSnapshot + EngagementSnapshot.
This reduces query load and supports the <200ms acceptance criteria for lead list loads.
When the feed is empty (e.g. before first run_update_lead_feed), both flows fall back to
the legacy join query. No behavior change for fractional CTO use case.
