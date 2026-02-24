# Multi-Tenant Briefing Scope (TODO)

**Status:** Not yet implemented. Tracked for when multi-workspace is enabled.

## Current State

- `get_briefing_data()` in `app/api/briefing_views.py` uses `get_default_pack_id(db)` for pack resolution.
- `get_emerging_companies()` is pack-scoped but not workspace-scoped.
- Briefing items, display scores, and emerging companies are not filtered by workspace.

## Required When Multi-Workspace Enabled

1. **Workspace context**: Briefing views must receive `workspace_id` (from session, URL, or tenant context).
2. **Pack resolution**: Use `get_pack_for_workspace(db, workspace_id)` instead of `get_default_pack_id(db)`.
3. **Data scoping**:
   - `get_emerging_companies(db, ..., pack_id=resolved_pack_id)` — already supports pack_id.
   - Briefing items may need workspace filter if stored per-workspace.
   - Display scores and ESL data are pack-scoped; verify no cross-workspace leakage.

## Reference

- TODO in code: `app/api/briefing_views.py` line ~121
- Pack resolver: `app/services/pack_resolver.get_pack_for_workspace`
- Pipeline stages: `docs/pipeline.md`
