# Diff-Based Monitor (Page Change Detection)

The **Diff-Based Monitor** is a pack-agnostic pipeline that watches company web pages (blog, careers, press, pricing, docs/changelog), stores page snapshots, detects content changes, and emits **Core Event candidates** via LLM classification. It does not replace the existing Scan or ingest flows; it is an additive, Core-owned flow. See the implementation plan (Issue #280) and the [SignalForge Architecture Contract](SignalForge%20Architecture%20Contract) (§2 Core Responsibilities: Monitoring & diff detection).

## What the Monitor Does

1. **Fetch** — Robots-aware fetch of company pages (blog, careers, press, pricing, docs/changelog) so crawls respect robots.txt.
2. **Snapshot** — Store page content in a dedicated snapshot store keyed by `(company_id, url)`; one row per URL updated on each fetch (or append-only by fetch time, per implementation).
3. **Diff** — Compare current content with the previous snapshot; produce a structured change event (before/after hash, diff summary, optional snippets).
4. **Interpret** — LLM interprets each change event and outputs candidate core event types (e.g. `pricing_changed`, `product_launch_detected`); every type is validated against the core taxonomy; invalid types are dropped.
5. **Emit** — Persist validated Core Event candidates as `SignalEvent` with `source="page_monitor"` and a deterministic `source_event_id` (e.g. hash of company_id + url + timestamp), so downstream derive/score consume them like other ingested events.

## What the Monitor Does Not Do

- **No** pack-specific logic — Snapshot storage, diff detection, and event type validation are pack-agnostic; no `pack_id` in monitor scope or snapshot/diff/interpretation logic.
- **No** replacement of Scan — Scan continues to discover pages, store `SignalRecord`, and update `company.cto_need_score`; the monitor is a parallel, optional path.
- **No** raw observation text to LLM by default — Only structured change events (diff summary, snippets) are passed to the interpretation LLM; implementation may limit or sanitize raw text for privacy and safety.

## Scope (URLs Monitored)

The monitor targets company-owned pages that often signal meaningful changes:

- **Blog** — `/blog`, `/news`: announcements, product updates
- **Careers** — `/careers`, `/jobs`: hiring signals
- **Press** — `/press`, `/media`: press releases
- **Pricing** — `/pricing`: pricing changes
- **Docs/changelog** — `/docs`, `/changelog`: product/API changes

Scope is defined in Core; packs do not configure which URLs are monitored.

## Relationship to Other Pipelines

- **Ingest → Derive → Score** — Events → `SignalEvent` → `SignalInstance` → ReadinessSnapshot, EngagementSnapshot
- **Scan** — Web scraping → `SignalRecord` → AnalysisRecord, `company.cto_need_score`
- **Discovery Scout** — LLM → Evidence Bundles only → `scout_runs`, `scout_evidence_bundles`
- **Diff-Based Monitor** — Snapshots → diff → LLM → Core Events → `SignalEvent` with `source="page_monitor"`

Monitor output feeds the same derive/score path as ingest: events are stored via `store_signal_event` and then derived and scored like other signal events. Idempotency is achieved via deterministic `source_event_id` so re-runs do not duplicate events.

## Entry Point and Auth

- **Endpoint (when implemented):** `POST /internal/run_monitor` — requires `X-Internal-Token`.
- **Parameters:** Optional `workspace_id`, optional `company_ids` (if empty, all companies with `website_url` in scope).
- **Response:** Counts and status (e.g. companies processed, change events found, events stored).

## Invariants (Architecture Contract)

- **workspace_id scoping** — Where applicable, monitor runs and event attribution are workspace-scoped; no cross-tenant leakage.
- **Core taxonomy only** — Every emitted event type is validated with `is_valid_core_event_type`; ESL hard bans cannot be bypassed.
- **Idempotency** — Deterministic `source_event_id` ensures re-runs do not create duplicate `SignalEvent` rows for the same change.

## References

- Implementation plan: Diff-Based Monitor Engine (Issue #280).
- Core event taxonomy: `app/core_taxonomy/`, `app/extractor/validation.py` (`is_valid_core_event_type`).
- Event storage: `app/ingestion/event_storage.py` (`store_signal_event`); monitor uses same path with `source="page_monitor"`.
- Pipeline overview: [pipeline.md](pipeline.md).
