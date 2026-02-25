# Phase 3: Multi-workspace briefing & outreach

Closes https://github.com/Disentangled-Tech/SignalForge/issues/225

## Summary

Implements Phase 3 (Pack Activation Runtime) of the company signal data models plan: briefing and outreach consistently pass `workspace_id` and `pack_id` when resolving scores and analyses. Enables multi-tenant workspace isolation when `MULTI_WORKSPACE_ENABLED=true`.

## Changes

### Briefing (`app/services/briefing.py`)
- **`_generate_for_company`**: Filters `AnalysisRecord` by pack (workspace's active pack or default); includes legacy rows with `workspace_id IS NULL` for default workspace
- Single pack resolution reused for analysis selection and `generate_outreach` (removes duplicate resolution)
- Existing-briefing check includes legacy `workspace_id IS NULL` when querying default workspace

### Outreach history (`app/services/outreach_history.py`)
- **`update_outreach_outcome`**: Accepts optional `workspace_id`; when provided, restricts updates to records in that workspace (same logic as `list_outreach`: match workspace or `NULL` when default)
- **`delete_outreach_record`**: Accepts optional `workspace_id`; when provided, restricts deletes to records in that workspace

### Views (`app/api/views.py`)
- **`_resolve_workspace_id(request)`**: Resolves `workspace_id` from `request.query_params` or `request.state` when `multi_workspace_enabled`; validates with `validate_uuid_param_or_422`
- **`_require_workspace_access(db, user, workspace_id)`**: Enforces workspace membership via `user_workspaces`; raises 403 when user lacks access (Phase 3)
- **`company_detail`**: Uses `_resolve_workspace_id`, `_require_workspace_access`; passes `workspace_id` to `list_outreach_for_company`, `get_draft_for_company`, `get_company_score`; scopes `analysis` and `briefing` by pack/workspace; passes `workspace_id` to template context
- **`companies_list`**: Resolves `workspace_id`, enforces access; passes to `list_companies` and `get_display_scores_for_companies`; adds `workspace_id` to template and links
- **`company_outreach_add`**: Resolves `workspace_id`; when `multi_workspace_enabled` and missing, defaults to `DEFAULT_WORKSPACE_ID` (prevents cross-tenant). Enforces access; passes to `create_outreach_record`; preserves `workspace_id` in redirect URLs
- **`company_outreach_edit`**: Same default; enforces access; passes to `update_outreach_outcome`; preserves in redirects
- **`company_outreach_delete`**: Same default; enforces access; passes to `delete_outreach_record`; preserves in redirects
- **`_company_redirect_url(company_id, params)`**: Builds redirect URLs with optional query params

### Outreach (`app/services/outreach.py`)
- **`generate_outreach`**: Preserves backward compat: `offer_type` fallback remains "fractional CTO" when pack unavailable (not "consultant")

### Score resolver (`app/services/score_resolver.py`)
- **`get_company_score`**, **`get_company_scores_batch`**: When `workspace_id` provided, resolve pack via `get_pack_for_workspace` (Phase 3); company detail and list now show correct pack-scoped scores for non-default workspaces

### Companies list (`app/templates/companies/list.html`)
- Company links and sort/pagination URLs include `?workspace_id=` when multi-workspace enabled

### Template (`app/templates/companies/detail.html`)
- Edit link, rescan form, outreach add form, outreach edit form, and outreach delete form append `?workspace_id={{ workspace_id }}` when `workspace_id` is present (multi-workspace mode)

### Migration (`alembic/versions/20260227_add_user_workspaces.py`)
- Creates `user_workspaces` (user_id, workspace_id) for workspace membership
- Backfills all existing users into default workspace

### Tests
- **`tests/test_outreach_history.py`**: `test_update_outreach_outcome_workspace_isolated`, `test_delete_outreach_record_workspace_isolated`
- **`tests/test_score_resolver.py`**: `test_get_company_score_uses_workspace_pack` — verifies `get_company_score` with `workspace_id` resolves pack from workspace
- **`tests/test_views.py`**: `test_forged_workspace_id_returns_403` — verifies 403 when user lacks workspace access

## Code review fixes (cross-tenant protection)

- **workspace_id default**: When `multi_workspace_enabled` and request has no `workspace_id` (e.g. direct POST without query params), views now default to `DEFAULT_WORKSPACE_ID` instead of passing `None`. Prevents cross-tenant modify/delete when workspace_id is missing.
- **offer_type fallback**: Restored "fractional CTO" as fallback when pack unavailable (preserves backward compat for fractional CTO flow).

## Verification

- [x] `pytest tests/test_outreach_history.py tests/test_ui_company_detail.py tests/test_views.py -v -k "outreach or company_detail"` — 27 passed
- [x] `ruff check` on modified app files — clean

## Risk

- **Low**: All changes additive; `workspace_id` optional with fallback to default when `multi_workspace_enabled` is false
