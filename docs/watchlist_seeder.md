# Watchlist Seeder (Issue #279)

The **Watchlist Seeder** turns verified evidence bundles into companies and Core Events, then feeds the same pipeline as ingestion: derive → score. It is pack-agnostic for event processing; pack selection affects only scoring.

---

## 1. Input

- **Bundle IDs** — One or more `evidence_bundles.id` (UUIDs) from the [Evidence Store](evidence-store.md). Bundles must have a valid `structured_payload` produced by the extractor (see [core_events schema](../app/schemas/core_events.py)).
- **Optional workspace_id** — When provided, bundles are loaded via `get_bundle_for_workspace(bundle_id, workspace_id)` so only bundles whose run belongs to that workspace are used. This enforces tenant boundaries. When omitted, `get_bundle(bundle_id)` is used and the caller must not pass other tenants’ bundle IDs.

---

## 2. Flow

1. **Register entities** — For each bundle, parse `structured_payload` and map `payload.company` (ExtractionEntityCompany) to `CompanyCreate`. Call `resolve_or_create_company()` so company resolution stays domain-based and consistent with ingest/API.
2. **Persist Core Events** — For each `payload.events` (CoreEventCandidate), create one `SignalEvent` row with:
   - `source = "watchlist_seeder"`
   - `source_event_id = "{bundle_id}:{index}"` for idempotent dedupe
   - `evidence_bundle_id = bundle_id` (optional FK for lineage)
   - `pack_id = None` (pack-agnostic; events are eligible for all pack scoring).
3. **Derive** — Run `run_deriver(db, workspace_id=..., pack_id=...)` as usual. It reads all `SignalEvent` rows (including seeder-originated), applies core derivers only, and upserts `SignalInstance` for the core pack.
4. **Score** — Run `run_score_nightly(db, workspace_id=..., pack_id=...)`. Eligibility already includes “companies with SignalEvents in last 365 days”; seeder-created events are included. Pack affects weights, ESL, and snapshot/lead_feed attribution only.

Orchestration (e.g. `POST /internal/run_watchlist_seed` or `scripts/run_watchlist_seed.py`) runs: **seed_from_bundles → run_deriver → run_score_nightly** in that order.

---

## 3. Dedupe

- **Events** — Dedupe is by `(source, source_event_id)`. The seeder uses a stable `source_event_id = "{bundle_id}:{index}"`, so re-seeding the same bundle does not create duplicate `SignalEvent` rows; `store_signal_event` returns `None` and the seeder counts them as `events_skipped_duplicate`.
- **Companies** — Company-side dedupe is domain-based in `resolve_or_create_company`; no change for the seeder.

---

## 4. Pack and scoring

- **Event processing** — The seeder does not depend on any pack. It does not set `SignalEvent.pack_id` (stores `None`), so events are visible to the deriver and to score eligibility regardless of pack.
- **Scoring** — Pack selection (workspace active pack or explicit `pack_id`) changes only how companies are scored: which weights, ESL rules, and recommendation bands apply. The **core SignalInstances** produced by the deriver are the same for all packs; acceptance tests assert “identical derive across packs” (same core instances; different snapshot scores/bands when scoring with pack A vs pack B).

---

## 5. API and scripts

- **Internal endpoint** — `POST /internal/run_watchlist_seed` (or `run_seed`) with body: `bundle_ids` (required), optional `workspace_id`, optional `pack_id`. Runs seed → derive → score and returns combined status plus seed/derive/score results.
- **Script** — `scripts/run_watchlist_seed.py` accepts bundle IDs (and optional workspace_id), uses `SessionLocal`, and runs the same sequence for CLI/cron.

---

## 6. References

- Implementation plan: Watchlist Seeder (Core Events → Derive → Score), milestones M1–M5.
- Evidence Store: [evidence-store.md](evidence-store.md).
- Deriver: [deriver-engine.md](deriver-engine.md).
- Core events schema: `app/schemas/core_events.py`; seeder result: `app/schemas/seeder.py`.
