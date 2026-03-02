# LLM Discovery Scout (Evidence-Only Mode)

The **Discovery Scout** is an LLM-powered flow that produces **Evidence Bundles only**: no signals, no domain-entity writes. It sits **outside** the ingest → derive → score pipeline and does not create companies, `SignalEvent` rows, or `SignalInstance` rows. Aligned with the Core + Pack Architecture Contract (§4) and the Evidence-Only implementation plan (Issue #275).

## What the Scout Does

1. **Query planning** — Uses ICP definition, core readiness signal rubric (from core taxonomy), and optional pack emphasis to produce diversified search queries.
2. **Source filtering** — Applies allowlist/denylist **before** fetching; denylist takes precedence.
3. **Page fetch** — Fetches pages from allowed sources only, with a configurable page limit.
4. **LLM extraction** — Calls the LLM with a prompt that requests structured **Evidence Bundle** output (citations, hypothesis, missing information).
5. **Validation** — Parses and validates output against the strict `EvidenceBundle` schema; citation rule: when `why_now_hypothesis` is non-empty, `evidence` must be non-empty.
6. **Verification (optional)** — When the verification gate is enabled, each validated bundle (and optional structured payload) is checked against pack-agnostic fact and event rules. Bundles that fail are quarantined with structured reason codes and are **not** stored; only passing bundles are sent to the Evidence Store. When the gate is disabled, all validated bundles proceed to persistence. See [Evidence Store — Verification Gate](evidence-store.md#62-verification-gate-issue-278).
7. **Persistence** — Writes only to scout-specific tables (`scout_runs`, `scout_evidence_bundles`). Raw model output and run metadata (model version, tokens, latency) are stored for audit. Evidence bundles that passed validation (and verification when enabled) are written to the Evidence Store via `store_evidence_bundle`.

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
| **workspace_id** | **Required** (API). Scopes the run to a tenant; stored on `scout_runs` for list/filter. |
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

## Optional Extractor (M4, Issue #277)

When enabled, the Scout run calls the **Evidence Extractor** per validated bundle before persisting to the Evidence Store. The Extractor produces normalized entities (Company, Person) and Core Event candidates only—no signal derivation. All extracted fields and events are source-backed (mapped to source_refs / source_ids). Its output is written into each bundle’s `structured_payload` in the Evidence Store.

- **Config:** `SCOUT_RUN_EXTRACTOR` in environment: set to `1`, `true`, or `yes` to enable; default is off (`0`). When off, `store_evidence_bundle` receives `structured_payloads=None` (current production behavior).
- **Override:** The service `run()` (and `DiscoveryScoutService.run()`) accept an optional parameter `run_extractor: bool | None = None`. If provided (True/False), it overrides the config value for that run; if `None`, config is used. The internal `POST /internal/run_scout` endpoint does not pass `run_extractor`, so production behavior is entirely config-driven.
- **Structured payload shape:** When the extractor runs, each bundle’s `structured_payload` in the Evidence Store has the ExtractionResult shape: `company` (normalized company), `person` (optional), `core_event_candidates` (list of core-event candidates, taxonomy-validated), and `version` (payload version string). See `app/extractor/schemas.py` and [evidence-store.md](evidence-store.md).

## Optional Event Interpretation (Issue #281)

When enabled (e.g. via config or run option), the Scout run can classify evidence into **core events** using an LLM interpretation step before or as part of extraction. The interpretation layer:

- **Input:** Raw content (e.g. evidence text, diff summary) plus optional evidence items for source_refs.
- **Output:** A list of **Core Event candidates** only; each `event_type` must be from the [core taxonomy](app/core_taxonomy/taxonomy.yaml). No new event types are invented—validation uses `is_valid_core_event_type` and drops any unknown type.
- **Pack-agnostic:** Pack selection does not alter interpretation result; the prompt and validation use the core taxonomy only. See Architecture Contract §4 (LLM Boundary Rules).
- **Reuse:** The same interpretation contract is shared by Scout (evidence → events) and the Diff-Based Monitor (ChangeEvent → events). See [event-interpretation.md](event-interpretation.md).

## Optional Verification Gate (Issue #278)

When enabled, the Scout run validates each evidence bundle (and optional structured payload) against the pack-agnostic Verification Gate before writing to the Evidence Store. Bundles that fail verification are quarantined with structured `reason_codes` and are **not** stored; only passing bundles are sent to `store_evidence_bundle`.

- **Config:** `SCOUT_VERIFICATION_GATE_ENABLED` in environment: set to `1`, `true`, or `yes` to enable; default is off (`0`). When off, all validated bundles are stored (current production behavior). When on, failed bundles go to `evidence_quarantine` with `payload.reason_codes` set.
- **Quarantine:** Failed bundles are written to `evidence_quarantine` with `payload.reason_codes` (list of strings) and `reason` set to a human-readable summary. See [evidence-store.md §6.2](evidence-store.md#62-verification-gate-issue-278).
- **Rules:** Event rules (event type in core taxonomy, timestamped citation, required fields) and fact rules (domain match, founder primary source, hiring jobs/ATS). See [evidence-store.md §6.2](evidence-store.md#62-verification-gate-issue-278) and `app/verification/`.

## Key Code Locations

| Area | Location |
| ---- | -------- |
| Schemas | `app/schemas/scout.py` — `EvidenceBundle`, `EvidenceItem`, `ScoutRunInput`, `RunScoutRequest`, `ScoutRunResult`, `ScoutRunMetadata`, `evidence_bundle_json_schema()` |
| Source filter | `app/scout/sources.py` — `is_source_allowed()`, `filter_allowed_sources()` |
| Query planner | `app/scout/query_planner.py` — `QueryPlanner`, `plan_queries()` |
| Config | `app/config.py` — `scout_source_allowlist`, `scout_source_denylist`, `scout_run_extractor`, `scout_verification_gate_enabled` |
| Event interpretation | `app/interpretation/` (schemas), `app/monitor/interpretation.py` (ChangeEvent → CoreEventCandidate); see [event-interpretation.md](event-interpretation.md) |

DiscoveryScoutService, persistence models, and the internal API are added in earlier milestones (M2–M5). This doc describes the full design; see the implementation plan for step-by-step milestones.

## Relationship to Other Pipelines

- **Ingest → Derive → Score:** Writes to `companies`, `signal_events`, `signal_instances`, snapshots. Scout does **not** use this path.
- **Scan:** Web scraping → `SignalRecord` → analysis/scoring for existing companies. Scout is independent; it discovers **candidates** and outputs evidence only.
- A future step may feed Evidence Bundles into a separate “evidence-to-events” pipeline (out of scope for the current Evidence-Only milestone). **Any such evidence-to-events step that writes SignalEvent rows from extractor output must enforce workspace (and optionally pack) when resolving company and writing events;** failure to scope would allow cross-tenant data.

## Schema (M3)

- **scout_runs:** run_id (UUID), workspace_id (nullable, FK to workspaces), started_at, finished_at, model_version, tokens_used, latency_ms, page_fetch_count, config_snapshot (JSONB), status, error_message.
- **scout_evidence_bundles:** scout_run_id (FK to scout_runs), candidate_company_name, company_website, why_now_hypothesis, evidence (JSONB), missing_information (JSONB), raw_llm_output (JSONB), created_at.

Indexes support list/filter by workspace and time/status: `(workspace_id, started_at DESC)`, `(workspace_id, status)`.

## Workspace (tenant) scoping

Scout runs are associated with a tenant via **workspace_id** on `scout_runs`. Until an API or UI exposes scout data:

- **Any future API or UI that lists or filters scout runs or evidence bundles must enforce workspace scoping:** require a valid workspace context (e.g. from auth or query param) and filter all queries with `WHERE workspace_id = :current_workspace_id`. Do not expose unscoped “list all scout runs” endpoints; that would allow cross-tenant data leakage.
- The internal scout endpoint `POST /internal/run_scout` **requires** `workspace_id` in the request body; it is stored on `scout_runs` so runs are always tenant-scoped.

## Sensitive data and access control

- **raw_llm_output** on `scout_evidence_bundles` stores the full LLM response for audit. It may contain PII or sensitive content.
- **When exposing scout data (runs or bundles) via any API or UI:** apply the same access control and audit expectations as for other LLM/audit data in the product (e.g. restrict to authorized callers, log access, treat as sensitive in compliance reviews).
- Do not expose `raw_llm_output` (or other scout fields) without enforcing workspace scoping and the same auth/audit as for similar data.

See [pipeline.md](pipeline.md) for the main pipeline; Scout is documented there as a separate flow.

## ADR / Architecture Contract

Scout aligns with **§4 LLM Boundary Rules**: outputs are citation-backed and schema-validated; it does not create new event or signal types.
