# Multi-Tenant Briefing Scope

**Status:** Implemented when `MULTI_WORKSPACE_ENABLED=true` (Issue #225).

## Current State

- `get_briefing_data(workspace_id=...)` accepts optional workspace_id.
- When `multi_workspace_enabled` and workspace_id provided: uses `get_pack_for_workspace(db, workspace_id)` for pack resolution; passes workspace_id to `get_emerging_companies()`.
- Briefing HTML: workspace_id from `?workspace_id=` query param or `request.state.workspace_id`.
- Briefing JSON API: workspace_id from `?workspace_id=` query param (when multi_workspace_enabled).

## Config

- `MULTI_WORKSPACE_ENABLED` (env): When "true", briefing/review scope by workspace_id. Default: false.

## Implemented (Issue #225)

- BriefingItem.workspace_id: nullable FK to workspaces; backfilled to default.
- generate_briefing(db, workspace_id=...) sets workspace_id on created items.
- select_top_companies(db, workspace_id=...) filters recently_briefed by workspace.
- get_briefing_data filters BriefingItem by workspace_id when provided.
- briefing_generate POST passes workspace_id when multi_workspace_enabled.

## Remaining (when multi-workspace fully enabled)
- Display scores and ESL data are pack-scoped; verify no cross-workspace leakage.

## Required Before Production (multi-workspace)

- **TODO: Workspace access control**: Add user–workspace membership (e.g. `user_workspaces` table or `User.workspace_id`) and enforce it in briefing endpoints. Without this, any authenticated user can pass any `workspace_id` and access that workspace's data. Do not enable `MULTI_WORKSPACE_ENABLED=true` in production until this is implemented.

## Reference

- Pack resolver: `app/services/pack_resolver.get_pack_for_workspace`
- Pipeline stages: `docs/pipeline.md`
