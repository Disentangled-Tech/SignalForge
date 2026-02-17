# Implementation Plan: Issue #50 — Edit Company Details

**Issue:** Add an Edit button to the company detail page. Make the fields editable and persistent in the DB.

**PRD alignment:** Company Detail page (rules/CURSOR_PRD.md) shows stored signals, analysis output, outreach draft, rescan button. Adding edit capability for company metadata fits the "company metadata" and "user notes" data handling rules. Jinja2 server-rendered pages, no React.

---

## Current State

### Existing Infrastructure (No Changes Needed)

| Component | Status |
|-----------|--------|
| `CompanyUpdate` schema | ✅ Exists with optional: company_name, website_url, founder_name, founder_linkedin_url, company_linkedin_url, notes, source, target_profile_match |
| `update_company(db, company_id, data)` | ✅ Implemented in `app/services/company.py` |
| `PUT /api/companies/{id}` | ✅ JSON API for updates (used by API clients) |
| `_schema_to_model_data()` | ✅ Handles company_name→name, target_profile_match→bool mapping |

### Company Detail Page

- **Route:** `GET /companies/{company_id}` → `app/templates/companies/detail.html`
- **Displayed fields:** company_name, website_url, founder_name, founder_linkedin_url, company_linkedin_url, source, last_scan_at, target_profile_match, notes, current_stage, cto_need_score
- **Actions:** Rescan, Delete

### Add Company Flow (Reference)

- `GET /companies/add` → form
- `POST /companies/add` → validate, create, redirect to detail with `?success=...` or error

---

## Editable vs Read-Only Fields

| Field | Editable | Notes |
|-------|----------|-------|
| company_name | ✅ | Required, max 255 |
| website_url | ✅ | Optional, validated URL |
| founder_name | ✅ | Optional |
| founder_linkedin_url | ✅ | Optional, validated URL |
| company_linkedin_url | ✅ | Optional, validated URL |
| notes | ✅ | Optional, text |
| source | ✅ | manual, referral, research |
| target_profile_match | ✅ | Checkbox (bool) |
| current_stage | ⚠️ Optional | LLM-derived; allow manual override for corrections |
| cto_need_score | ❌ | Computed from analysis |
| last_scan_at | ❌ | Set by scan job |
| created_at / updated_at | ❌ | System-managed |

---

## Implementation Plan

### Phase 1: Schema Extensions (Optional)

**File:** `app/schemas/company.py`

- Add `current_stage: Optional[str] = Field(None, max_length=64)` to `CompanyUpdate` if user wants manual stage override.
- **Recommendation:** Add it; useful when LLM stage is wrong and user wants to correct.

### Phase 2: View Routes

**File:** `app/api/views.py`

1. **Import** `update_company` from `app.services.company` and `CompanyUpdate`, `CompanySource` from `app.schemas.company`.

2. **GET /companies/{company_id}/edit** — Render edit form with pre-filled company data.
   - Auth: `_require_ui_auth`
   - 404 if company not found
   - Pass `company` (CompanyRead) to template as `form_data` for pre-fill (map company_name→company_name, etc.)

3. **POST /companies/{company_id}/edit** — Handle form submission.
   - Form params: company_name, website_url, founder_name, founder_linkedin_url, company_linkedin_url, notes, source, target_profile_match (checkbox: "on" = True), current_stage (if added)
   - Validation: same as add (company_name required, URL validation via `_is_valid_url`)
   - On success: `update_company(db, company_id, CompanyUpdate(...))` → redirect to `/companies/{id}?success=Company+updated`
   - On validation error: re-render edit form with `form_data` and `errors`
   - 404 if company not found

### Phase 3: Edit Template

**File:** `app/templates/companies/edit.html` (new)

- Extend `base.html`, mirror structure of `add.html`
- Same form fields as add, plus:
  - `target_profile_match` checkbox (checked when `company.target_profile_match` is truthy)
  - `current_stage` text input (optional, if added to schema)
- Form action: `POST /companies/{{ company.id }}/edit`
- Pre-fill from `form_data` (company)
- Cancel link: `/companies/{{ company.id }}`

### Phase 4: Detail Page — Add Edit Button

**File:** `app/templates/companies/detail.html`

- Add Edit button next to Rescan and Delete:
  - `<a href="/companies/{{ company.id }}/edit" class="btn btn-secondary">Edit</a>`
- Or as a link: "Edit" next to the header
- Handle `?success=Company+updated` query param for flash message (same pattern as settings)

### Phase 5: Tests (TDD)

**File:** `tests/test_views.py`

1. **GET /companies/1/edit** — Renders form with company data pre-filled; 404 for non-existent company.
2. **GET /companies/1/edit** — Unauthenticated redirects to login.
3. **POST /companies/1/edit** — Valid data updates company and redirects to detail with success.
4. **POST /companies/1/edit** — Empty company_name returns 422 with error.
5. **POST /companies/1/edit** — Invalid URL returns 422 with error.
6. **POST /companies/999/edit** — Returns 404.

**File:** `tests/test_company_service.py` (if needed)

- `update_company` already tested; no new tests required unless schema changes.

---

## Security & Privacy

- **Auth:** Edit requires same UI auth as detail (cookie-based).
- **Validation:** Reuse `_is_valid_url`; reject empty company_name; validate source enum.
- **Data:** Only company metadata; no sensitive data. Notes are user-provided per PRD.

---

## File Summary

| File | Action |
|------|--------|
| `app/schemas/company.py` | Add `current_stage` to CompanyUpdate (optional) |
| `app/api/views.py` | Add GET/POST handlers for edit |
| `app/templates/companies/edit.html` | New file |
| `app/templates/companies/detail.html` | Add Edit button, optional success flash |
| `tests/test_views.py` | Add TestCompanyEdit class |

---

## Rollback & Compatibility

- No DB migrations.
- No changes to API routes.
- Existing `update_company` and `CompanyUpdate` unchanged except optional `current_stage`.
- Edit form is additive; existing flows unchanged.

---

## Order of Implementation (TDD)

1. Write tests for GET/POST edit (fail first).
2. Add schema change (current_stage) if desired.
3. Add view routes.
4. Create edit template.
5. Add Edit button to detail page.
6. Run tests.
7. Run Snyk code scan per project rules.
