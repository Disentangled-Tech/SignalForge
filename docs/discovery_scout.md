# LLM Discovery Scout (Evidence-Only Mode)

The Discovery Scout is a **separate flow** from the main pipeline (ingest → derive → score). It uses the LLM to produce **Evidence Bundles** only: no signals, no domain-entity writes, no pack-specific derivation.

## What the Scout does

- **Inputs:** ICP definition, optional exclusion rules, optional pack_id (for query emphasis only), optional page_fetch_limit.
- **Process:** Query planning (from core taxonomy + optional pack emphasis) → LLM call with a structured prompt → parse and validate output against the Evidence Bundle schema → persist to `scout_runs` and `scout_evidence_bundles`.
- **Output:** Run metadata (run_id, status, bundles_count) and validated Evidence Bundles (candidate_company_name, company_website, why_now_hypothesis, evidence list, missing_information). Citation rule: when `why_now_hypothesis` is non-empty, at least one evidence item is required.

## What the Scout does not do

- Does **not** write to `companies`, `signal_events`, or `signal_instances`.
- Does **not** call `resolve_or_create_company`, `store_signal_event`, or any deriver.
- Does **not** run as a pipeline stage (not in `STAGE_REGISTRY` or `run_daily_aggregation`).
- Does **not** scope by workspace_id; it is pack-agnostic (pack_id is for query phrasing only).

## How to run

- **Endpoint:** `POST /internal/run_scout` (requires `X-Internal-Token` header).
- **Body (JSON):** `icp_definition` (required), `exclusion_rules` (optional), `pack_id` (optional), `page_fetch_limit` (optional, default 10, range 0–100).
- **Config:** `SCOUT_SOURCE_ALLOWLIST` and `SCOUT_SOURCE_DENYLIST` (comma-separated domains) control source filtering when URL fetching is used; denylist takes precedence.

## Schema and storage

- Evidence Bundle schema: see `app/schemas/scout.py` (`EvidenceBundle`, `EvidenceItem`). JSON schema export via `evidence_bundle_json_schema()`.
- Tables: `scout_runs` (run metadata), `scout_evidence_bundles` (one row per bundle). No foreign keys to companies or signal_events.
