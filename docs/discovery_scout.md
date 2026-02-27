# Discovery Scout (Evidence-Only Mode)

The **LLM Discovery Scout** produces **Evidence Bundles** only: no signals, no domain-entity writes (no companies, no `signal_events`). It is a separate flow from the ingest → derive → score pipeline. See Issue #275 and the implementation plan.

## What the Scout Does

- **Inputs:** ICP definition, core readiness rubric (read-only), optional pack_id for query emphasis, source allowlist/denylist.
- **Output:** Structured Evidence Bundles (candidate company name, website, why-now hypothesis, evidence citations, missing information) persisted to `scout_runs` and `scout_evidence_bundles`.
- **Does not:** Create companies, create signal events, run derivers, or write to `signal_instances` or pack-scoped snapshots.

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

## Relationship to pipeline

Scout is **not** a stage in the ingest → derive → score pipeline. It is invoked separately (e.g. future internal endpoint or script). It does not write to `companies`, `signal_events`, or `signal_instances`. See [pipeline.md](pipeline.md) for the main pipeline; Scout is out of scope there.

## ADR / Architecture Contract

Scout aligns with **§4 LLM Boundary Rules**: outputs are citation-backed and schema-validated; it does not create new event or signal types.
