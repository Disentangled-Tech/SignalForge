# LLM Discovery Scout (Evidence-Only Mode)

The **Discovery Scout** is an LLM-powered flow that produces **Evidence Bundles only**: no signals, no domain-entity writes. It sits **outside** the ingest → derive → score pipeline and does not create companies, `SignalEvent` rows, or `SignalInstance` rows. Aligned with the Core + Pack Architecture Contract (§4) and the Evidence-Only implementation plan.

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
| Schemas | `app/schemas/scout.py` — `EvidenceBundle`, `EvidenceItem`, `ScoutRunInput`, `ScoutRunResult`, `ScoutRunMetadata`, `evidence_bundle_json_schema()` |
| Source filter | `app/scout/sources.py` — `is_source_allowed()`, `filter_allowed_sources()` |
| Config | `app/config.py` — `scout_source_allowlist`, `scout_source_denylist` |

Query Planner, DiscoveryScoutService, persistence models, and the internal API are added in earlier milestones (M2–M5). This doc describes the full design; see the implementation plan for step-by-step milestones.

## Relationship to Other Pipelines

- **Ingest → Derive → Score:** Writes to `companies`, `signal_events`, `signal_instances`, snapshots. Scout does **not** use this path.
- **Scan:** Web scraping → `SignalRecord` → analysis/scoring for existing companies. Scout is independent; it discovers **candidates** and outputs evidence only.
- A future step may feed Evidence Bundles into a separate “evidence-to-events” pipeline (out of scope for the current Evidence-Only milestone).
