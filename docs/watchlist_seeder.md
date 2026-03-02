# Watchlist Seeder (Issue #279)

The **Watchlist Seeder** registers entities and Core Events from verified evidence bundles, persists them as `SignalEvent` rows, and integrates with the existing derive and score pipeline. It provides a second path (alongside ingestion) for getting observations into the system.

## Input

- **Bundle IDs** — One or more `evidence_bundles.id` (UUIDs) from the [Evidence Store](evidence-store.md). Bundles must contain a valid `structured_payload` (extractor output) with at least a company and one or more Core Event candidates.
- **Workspace ID** (optional) — When provided, bundle loading is workspace-scoped via `get_bundle_for_workspace(bundle_id, workspace_id)`, enforcing tenant isolation in multi-tenant mode.

## Flow

1. **Load bundles** — For each `bundle_id`, load the bundle (optionally workspace-scoped). Parse `structured_payload` as `StructuredExtractionPayload` (company + events).
2. **Register entity** — Map `payload.company` to `CompanyCreate` and call `resolve_or_create_company()` (domain-based dedupe). Obtain `company_id`.
3. **Persist Core Events** — For each Core Event candidate in `payload.events`, map to `SignalEvent` shape and call `store_signal_event(..., source="watchlist_seeder", source_event_id=..., evidence_bundle_id=bundle_id)`.
4. **Downstream** — After seeding, run **derive** then **score** (e.g. via `POST /internal/run_watchlist_seed` or `scripts/run_watchlist_seed.py`). Derive populates `signal_instances` from the new events; score updates readiness/engagement snapshots and lead feed.

See [deriver-engine.md](deriver-engine.md) and [signal-models.md](signal-models.md) for the derive and score stages.

## Dedupe and idempotency

- **Events** — Dedupe is by `(source, source_event_id)`. The seeder uses a stable `source_event_id` per event (e.g. `{bundle_id}:{event_index}`). Re-seeding the same bundle does not create duplicate `SignalEvent` rows; `store_signal_event` skips duplicates and the result reports `events_skipped_duplicate`.
- **Companies** — Company resolution is domain-based via `resolve_or_create_company`; re-seeding reuses the same company when the payload company domain matches.

## Pack and scoring

- **Derive** — Uses **core derivers only**; no pack dependency for event processing. The same Core Events produce the same set of derived signals regardless of pack.
- **Score** — Pack selection affects **scoring only** (weights, ESL, bands). Eligibility already includes companies with `SignalEvent` activity in the last 365 days; seeder-created events are included. Different packs yield different snapshot scores/bands; the underlying `SignalInstance` set from derive is identical across packs for the same events.

## API and script

- **Internal endpoint** — `POST /internal/run_watchlist_seed` with body: `bundle_ids` (required), optional `workspace_id`, optional `pack_id`. Runs seed → derive → score and returns combined status and counts.
- **Script** — `scripts/run_watchlist_seed.py` accepts bundle IDs (and optional workspace_id); uses the same flow for CLI/cron use.

## Related

- [Evidence Store](evidence-store.md) — Bundle schema and repository.
- [Deriver Engine](deriver-engine.md) — Core derivers only; pack does not affect derivation.
- [Core vs Pack Responsibilities](CORE_VS_PACK_RESPONSIBILITIES.md) — What is core vs pack-scoped.
