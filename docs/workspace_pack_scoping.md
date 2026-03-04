# Workspace and Pack Scoping (Issue #193)

All tenant-visible data access is scoped by **workspace_id**. All signal and snapshot access is scoped by **pack_id**.

## Workspace scoping

- **Tenant-visible data** (lead feed, briefing items, outreach history, scout runs, evidence bundles) is filtered by `workspace_id` at API and service entry points. A caller must supply a workspace (or a default is used for single-tenant/internal jobs) so that one tenant never sees another tenant’s data.
- **Internal jobs** (`/internal/*`) accept optional `workspace_id` (and `pack_id` where applicable); when omitted, the default workspace is used so existing single-tenant and cron flows continue to work.

## Pack scoping

- **SignalEvent**, **ReadinessSnapshot**, **EngagementSnapshot**, and **SignalInstance** are pack-scoped. Queries and writes use an explicit `pack_id` (resolved from the workspace’s active pack or passed in). After Issue #193 M1, `pack_id` is NOT NULL on `signal_events`, `readiness_snapshots`, and `engagement_snapshots`; there is no “default pack” NULL in those tables.
- **Lead feed**, **score**, and **briefing** paths resolve pack from workspace (e.g. `get_pack_for_workspace(db, workspace_id)`) and filter all snapshot/signal reads by that pack so pack A never sees pack B’s data.

## References

- [Issue #193](https://github.com/Disentangled-Tech/SignalForge/issues/193) — Enforce workspace and pack scoping across all data access.
- [signal-models.md](signal-models.md) — Pack-scoped signal tables and AnalysisRecord.
- [pipeline.md](pipeline.md) — Stage and API behavior (workspace/pack params).
