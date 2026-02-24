# Pipeline Stages

Stages are invoked via `/internal/*` endpoints (cron or scripts). Each stage is workspace- and pack-scoped.

| Stage | Endpoint | Description | Idempotency |
|-------|----------|-------------|-------------|
| **ingest** | `POST /internal/run_ingest` | Fetch raw events, normalize, resolve companies, store `signal_events` | Dedup by `(source, source_event_id)` |
| **derive** | `POST /internal/run_derive` | Populate `signal_instances` from `SignalEvents` using pack derivers | Upsert by `(entity_id, signal_id, pack_id)` |
| **score** | `POST /internal/run_score` | Compute TRS + ESL, write `ReadinessSnapshot` + `EngagementSnapshot` | Upsert by `(company_id, as_of, pack_id)` |
| **update_lead_feed** | `POST /internal/run_update_lead_feed` | Project `lead_feed` from snapshots | Upsert by `(workspace_id, entity_id, pack_id)` |

## API Behavior

### POST /internal/run_derive

- **Requires a pack**: The derive stage requires a pack to be available (default pack or explicit `pack_id`). If no pack is installed or resolvable, the endpoint returns **400 Bad Request** with detail `"Derive stage requires a pack; no pack available"`.
- **Cron/script impact**: Callers that previously received 200 with `status: "skipped"` when no pack existed will now receive 400. Ensure migrations have run and the fractional_cto_v1 pack is installed before invoking derive.
