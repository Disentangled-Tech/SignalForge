# LLM Discovery Scout (Evidence-Only Mode)

The **Discovery Scout** is an LLM-powered flow that produces **Evidence Bundles only**: no signals, no domain-entity writes. It sits **outside** the ingest → derive → score pipeline and does not create companies, `SignalEvent` rows, or `SignalInstance` rows. Aligned with the Core + Pack Architecture Contract (§4) and the Evidence-Only implementation plan (Issue #275).

## What the Scout Does

1. **Query planning** — Uses ICP definition, core readiness signal rubric (from core taxonomy), and optional pack emphasis to produce diversified search queries.
2. **Source filtering** — Applies allowlist/denylist **before** fetching; denylist takes precedence.
3. **Page fetch** — Fetches pages from allowed sources only, with a configurable page limit.
4. **LLM extraction** — Calls the LLM with a prompt that requests structured **Evidence Bundle** output (citations, hypothesis, missing information).
5. **Validation** — Parses and validates output against the strict `EvidenceBundle` schema; citation rule: when `why_now_hypothesis` is non-empty, `evidence` must be non-empty.
6. **Persistence** — Writes only to scout-specific tables (`scout_runs`, `scout_evidence_bundles`). Raw model output and run metadata (model version, tokens, latency) are stored for audit.

## What the Scout Does Not Do

- **No** company creation or resolution (`resolve_or_create_company`).
- **No** event storage (`store_signal_event`).
- **No** signal derivation or pack-specific derivation.
- **No** writes to `companies`, `signal_events`, or `signal_instances`.
- **No** addition to `STAGE_REGISTRY` or `run_daily_aggregation` — Scout runs as a **separate flow** triggered by its own internal endpoint (or script).

## Inputs

| Input | Description |
| ----- | ----------- |
| **ICP definition** | Text description of ideal customer profile; used by the Query Planner to phrase search queries. |
| **Exclusion rules** | Optional text; can inform allowlist/denylist or downstream filtering. |
| **Allowlist / denylist** | Config (e.g. `SCOUT_SOURCE_ALLOWLIST`, `SCOUT_SOURCE_DENYLIST` in env or `app/config.py`). Denylist blocks domains/URLs; empty allowlist = all allowed (subject to denylist). |
| **pack_id** | Optional. Used only for **query emphasis hints** (e.g. pack-specific keywords), not for derivation or storage. |
| **page_fetch_limit** | Optional cap on number of pages fetched per run. |

## Output Schema

Scout output is **Evidence Bundles** only:

- **EvidenceBundle** (per candidate):
  - `candidate_company_name`, `company_website`
  - `why_now_hypothesis` (claim; must be backed by evidence when non-empty)
  - `evidence[]`: each item has `url`, `quoted_snippet`, `timestamp_seen`, `source_type`, `confidence_score`
  - `missing_information[]`: list of strings

No `signal_id`, `event_type`, or pack-specific fields. JSON schema is available via `evidence_bundle_json_schema()` in `app/schemas/scout.py` for LLM output validation.

## How to Run

- **Internal endpoint (when implemented):** `POST /internal/run_scout` (or `/internal/run_discovery_scout`) with body: ICP, exclusion rules, optional `pack_id`, optional `page_fetch_limit`. Requires `X-Internal-Token` header.
- **Config:** Set `SCOUT_SOURCE_ALLOWLIST` and/or `SCOUT_SOURCE_DENYLIST` (comma-separated domains) in environment or via `app/config.py` to restrict which sources are fetched.

## Key Code Locations

| Area | Location |
| ---- | -------- |
| Schemas | `app/schemas/scout.py` — `EvidenceBundle`, `EvidenceItem`, `ScoutRunInput`, `RunScoutRequest`, `ScoutRunResult`, `ScoutRunMetadata`, `evidence_bundle_json_schema()` |
| Source filter | `app/scout/sources.py` — `is_source_allowed()`, `filter_allowed_sources()` |
| Query planner | `app/scout/query_planner.py` — `QueryPlanner`, `plan_queries()` |
| Config | `app/config.py` — `scout_source_allowlist`, `scout_source_denylist` |

DiscoveryScoutService, persistence models, and the internal API are added in earlier milestones (M2–M5). This doc describes the full design; see the implementation plan for step-by-step milestones.

## Relationship to Other Pipelines

- **Ingest → Derive → Score:** Writes to `companies`, `signal_events`, `signal_instances`, snapshots. Scout does **not** use this path.
- **Scan:** Web scraping → `SignalRecord` → analysis/scoring for existing companies. Scout is independent; it discovers **candidates** and outputs evidence only.
- A future step may feed Evidence Bundles into a separate “evidence-to-events” pipeline (out of scope for the current Evidence-Only milestone).
## Schema (M3)

- **scout_runs:** run_id (UUID), workspace_id (nullable, FK to workspaces), started_at, finished_at, model_version, tokens_used, latency_ms, page_fetch_count, config_snapshot (JSONB), status, error_message.
- **scout_evidence_bundles:** scout_run_id (FK to scout_runs), candidate_company_name, company_website, why_now_hypothesis, evidence (JSONB), missing_information (JSONB), raw_llm_output (JSONB), created_at.

Indexes support list/filter by workspace and time/status: `(workspace_id, started_at DESC)`, `(workspace_id, status)`.

## Workspace (tenant) scoping

Scout runs are associated with a tenant via **workspace_id** on `scout_runs`. Until an API or UI exposes scout data:

- **Any future API or UI that lists or filters scout runs or evidence bundles must enforce workspace scoping:** require a valid workspace context (e.g. from auth or query param) and filter all queries with `WHERE workspace_id = :current_workspace_id`. Do not expose unscoped “list all scout runs” endpoints; that would allow cross-tenant data leakage.
- When adding the internal scout endpoint (e.g. `POST /internal/run_scout`), require and store `workspace_id` so runs are always tenant-scoped.

## Sensitive data and access control

- **raw_llm_output** on `scout_evidence_bundles` stores the full LLM response for audit. It may contain PII or sensitive content.
- **When exposing scout data (runs or bundles) via any API or UI:** apply the same access control and audit expectations as for other LLM/audit data in the product (e.g. restrict to authorized callers, log access, treat as sensitive in compliance reviews).
- Do not expose `raw_llm_output` (or other scout fields) without enforcing workspace scoping and the same auth/audit as for similar data.

See [pipeline.md](pipeline.md) for the main pipeline; Scout is documented there as a separate flow.

## ADR / Architecture Contract

Scout aligns with **§4 LLM Boundary Rules**: outputs are citation-backed and schema-validated; it does not create new event or signal types.
