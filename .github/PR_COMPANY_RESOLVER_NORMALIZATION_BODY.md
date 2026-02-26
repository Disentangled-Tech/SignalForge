# Company Resolver Pure Normalization Layer (Issue #88)

Closes https://github.com/Disentangled-Tech/SignalForge/issues/88

## Summary

Adds a pure normalization layer to the company resolver for deterministic matching and unit-testable logic. Extracts `normalize_company_input` and `NormalizedCompanyInput`; refactors `resolve_or_create_company` to use them internally. Behavior unchanged.

## Changes

### `app/services/company_resolver.py`
- **`NormalizedCompanyInput`** TypedDict: `{domain, norm_name, linkedin}` — output of normalization
- **`normalize_company_input(data: CompanyCreate)`**: Pure function, no DB; returns normalized domain, norm_name, linkedin
- **`resolve_or_create_company`**: Uses `normalize_company_input` internally; resolution order unchanged
- **`__all__`**: Exports `normalize_company_input`, `NormalizedCompanyInput`, `extract_domain`, `normalize_name`, `resolve_or_create_company`

### `tests/test_company_resolver.py`
- **`TestNormalizeCompanyInput`**: 6 pure unit tests (no DB) for domain, norm_name, linkedin, empty linkedin, all fields, whitespace-only name
- Removed unused imports: `datetime`, `timezone`, `MagicMock`, `CompanySource`
- Formatting: single-line method signatures where appropriate

## Verification

- [x] `pytest tests/test_company_resolver.py tests/test_ingestion_adapter.py -v -W error`
- [x] `ruff check` on modified files — clean

## Risk

- **Low**: Additive; `resolve_or_create_company` behavior identical; pure functions are unit-testable without DB
