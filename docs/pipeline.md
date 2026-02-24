# Event-Driven Pipeline (Issue #192)

This document describes the pipeline stages, idempotency guarantees, and rate limits for the SignalForge event-driven job system.

## Pipeline Stages

Stages are invoked via `/internal/*` endpoints (cron or scripts). Each stage is workspace- and pack-scoped.

| Stage | Endpoint | Description | Idempotency |
|-------|----------|-------------|-------------|
| **ingest** | `POST /internal/run_ingest` | Fetch raw events, normalize, resolve companies, store `signal_events` | Dedup by `(source, source_event_id)` |
| **derive** | `POST /internal/run_derive` | Populate `signal_instances` from `SignalEvents` using pack derivers | Upsert by `(entity_id, signal_id, pack_id)` |
| **score** | `POST /internal/run_score` | Compute TRS + ESL, write `ReadinessSnapshot` + `EngagementSnapshot` | Upsert by `(company_id, as_of, pack_id)` |
| **update_lead_feed** | `POST /internal/run_update_lead_feed` | Project `lead_feed` from snapshots | Upsert by `(workspace_id, entity_id, pack_id)` |

### Stage Flow

```
ingest → derive → score → update_lead_feed
```

- **ingest**: Adapters fetch raw events; normalize validates against pack taxonomy; store deduplicates.
- **derive**: Applies pack `derivers.passthrough` (event_type → signal_id); upserts `signal_instances`.
- **score**: Computes readiness (TRS) and engagement (ESL); writes snapshots.
- **update_lead_feed**: Joins snapshots, computes outreach score; upserts `lead_feed` for briefing.

### Implementation

- **Protocol**: `app/pipeline/stages.py` defines `PipelineStage` and `STAGE_REGISTRY`.
- **Executor**: `app/pipeline/executor.py` — `run_stage(job_type, workspace_id, pack_id, idempotency_key)`.
- **Default workspace**: `00000000-0000-0000-0000-000000000001` until multi-workspace.
- **Default pack**: Resolved via `get_default_pack_id(db)` when not provided.

---

## Idempotency Guarantees

### Job-Level Idempotency

Pass `X-Idempotency-Key` header when calling internal endpoints. If a completed run exists for the same `(idempotency_key, job_type, workspace_id)`, the executor returns the cached result without re-running.

- **Scope**: Idempotency keys are workspace-scoped. Use `{workspace_id}:{timestamp}` to avoid collisions.
- **Cached response**: Approximate; `JobRun` does not store all stage-specific fields (e.g. `skipped_duplicate`); cached values may be 0.

### Stage-Level Idempotency

Each stage is designed to be safe to re-run:

| Stage | Mechanism |
|-------|-----------|
| ingest | `store_signal_event` deduplicates by `(source, source_event_id)` |
| derive | Upsert `signal_instances` by `(entity_id, signal_id, pack_id)` |
| score | Upsert snapshots by `(company_id, as_of, pack_id)` |
| update_lead_feed | Upsert `lead_feed` by `(workspace_id, entity_id, pack_id)` |

Re-running a stage produces the same final state; no duplicate rows.

---

## Rate Limits

Per-workspace rate limits apply before stage execution.

- **Config**: `WORKSPACE_JOB_RATE_LIMIT_PER_HOUR` (default: 10). Set to `0` to disable.
- **Scope**: Counts `JobRun` rows per `(workspace_id, job_type)` in the last hour.
- **Behavior**: If limit exceeded, executor raises `HTTP 429` with detail `"Workspace job rate limit exceeded"`.
- **Module**: `app/pipeline/rate_limits.py` — `check_workspace_rate_limit(db, workspace_id, job_type)`.

---

## Security

- **Internal endpoints**: Require `X-Internal-Token` header (constant-time comparison).
- **Workspace scoping**: Jobs record `workspace_id`; stages scope by workspace.
- **Pack scoping**: Jobs record `pack_id`; stages scope by pack.
