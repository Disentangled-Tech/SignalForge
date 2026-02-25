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
- **`company_detail`**: Uses `_resolve_workspace_id`, passes `workspace_id` to `list_outreach_for_company`, `get_draft_for_company`, `get_company_score`; passes `workspace_id` to template context
- **`company_outreach_add`**: Resolves `workspace_id`, passes to `create_outreach_record`; preserves `workspace_id` in redirect URLs
- **`company_outreach_edit`**: Resolves `workspace_id`, passes to `update_outreach_outcome`; preserves in redirects
- **`company_outreach_delete`**: Resolves `workspace_id`, passes to `delete_outreach_record`; preserves in redirects
- **`_company_redirect_url(company_id, params)`**: Builds redirect URLs with optional query params

### Template (`app/templates/companies/detail.html`)
- Edit link, rescan form, outreach add form, outreach edit form, and outreach delete form append `?workspace_id={{ workspace_id }}` when `workspace_id` is present (multi-workspace mode)

### Tests (`tests/test_outreach_history.py`)
- **`test_update_outreach_outcome_workspace_isolated`**: Verifies `update_outreach_outcome` with `workspace_id` only updates records in that workspace
- **`test_delete_outreach_record_workspace_isolated`**: Verifies `delete_outreach_record` with `workspace_id` only deletes records in that workspace

## Verification

- [x] `pytest tests/test_outreach_history.py tests/test_ui_company_detail.py tests/test_views.py -v -k "outreach or company_detail"` — 27 passed
- [x] `ruff check` on modified app files — clean

## Risk

- **Low**: All changes additive; `workspace_id` optional with fallback to default when `multi_workspace_enabled` is false
