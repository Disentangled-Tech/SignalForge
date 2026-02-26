# Company Resolver: normalize_company_input Refactor (Issue #88)

Closes https://github.com/Disentangled-Tech/SignalForge/issues/88

## Summary

Refactors company resolution to extract pure normalization logic into `normalize_company_input()`. Improves testability and keeps resolution behavior identical.

## Changes

### `app/services/company_resolver.py`
- **`NormalizedCompanyInput`** (TypedDict): Output shape for normalization
- **`normalize_company_input(data: CompanyCreate)`**: Pure function returning `{domain, norm_name, linkedin}` — no DB
- **`resolve_or_create_company`**: Uses `normalize_company_input()` instead of inline logic; behavior unchanged

### `tests/test_company_resolver.py`
- **`TestNormalizeCompanyInput`**: 6 pure unit tests (no DB)
- Removed unused `CompanySource` import
- **`@pytest.mark.serial`** on `TestResolveOrCreateCompany` to avoid ShareLock deadlock with pytest-xdist
- Formatting: method signatures on single line

### `pyproject.toml`
- Registered `serial` marker for tests that must run serially

## Verification

- [x] `pytest tests/test_company_resolver.py -v -W error` — 26 passed
- [x] `ruff check app/services/company_resolver.py tests/test_company_resolver.py` — clean

## Risk

- **Low**: Refactor only; resolution order and logic unchanged
- **Backward compatible**: Same inputs produce same outputs
