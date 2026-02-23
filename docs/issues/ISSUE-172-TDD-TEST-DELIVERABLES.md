# Issue #172 — Signal Pack Loader with Manifest + Schema Validation: TDD Test Deliverables

## 1. Test Inventory

### New Tests Added

| File | Test | Purpose |
|------|------|---------|
| `tests/test_pack_schema_validation.py` | `test_valid_full_pack_passes` | Valid pack config passes validation |
| `tests/test_pack_schema_validation.py` | `test_valid_minimal_pack_passes` | Minimal required structure passes |
| `tests/test_pack_schema_validation.py` | `test_missing_id_raises` | Manifest without id raises ValidationError |
| `tests/test_pack_schema_validation.py` | `test_missing_version_raises` | Manifest without version raises |
| `tests/test_pack_schema_validation.py` | `test_missing_name_raises` | Manifest without name raises |
| `tests/test_pack_schema_validation.py` | `test_empty_manifest_raises` | Empty manifest raises |
| `tests/test_pack_schema_validation.py` | `test_missing_signal_ids_raises` | Taxonomy without signal_ids raises |
| `tests/test_pack_schema_validation.py` | `test_empty_signal_ids_raises` | Empty signal_ids raises |
| `tests/test_pack_schema_validation.py` | `test_scoring_references_unknown_signal_raises` | Scoring refs unknown signal → ValidationError |
| `tests/test_pack_schema_validation.py` | `test_scoring_dimension_with_all_invalid_signals_raises` | Scoring dimension with no valid refs raises |
| `tests/test_pack_schema_validation.py` | `test_deriver_signal_id_not_in_taxonomy_raises` | Deriver signal_id not in taxonomy raises |
| `tests/test_pack_schema_validation.py` | `test_deriver_missing_signal_id_raises` | Deriver passthrough without signal_id raises |
| `tests/test_pack_schema_validation.py` | `test_svi_event_types_reference_unknown_signal_raises` | ESL svi_event_types ref unknown signal raises |
| `tests/test_pack_schema_validation.py` | `test_empty_svi_event_types_allowed` | Empty svi_event_types is allowed |
| `tests/test_pack_schema_validation.py` | `test_validation_error_is_exception` | ValidationError subclasses Exception |
| `tests/test_pack_schema_validation.py` | `test_validation_error_message_preserved` | ValidationError preserves message |
| `tests/test_pack_loader.py` | `test_load_pack_returns_derivers` | Pack has derivers attribute with passthrough |
| `tests/test_pack_loader.py` | `test_derivers_match_taxonomy_signal_ids` | All deriver signal_ids in taxonomy |
| `tests/test_pack_loader.py` | `test_load_invalid_schema_pack_raises_validation_error` | load_pack invalid_schema_pack raises ValidationError |
| `tests/test_pack_loader.py` | `test_invalid_pack_error_message_mentions_problem` | Error message includes ghost_signal/taxonomy |
| `tests/test_pack_resolver.py` | `test_resolve_pack_returns_none_when_validation_fails` | resolve_pack returns None when pack invalid |
| `tests/test_ui_pack_metadata.py` | `test_settings_shows_active_pack_section` | Settings page shows active pack metadata |
| `tests/test_ui_pack_metadata.py` | `test_settings_pack_section_includes_version` | Pack section shows version when present |
| `tests/test_ui_pack_metadata.py` | `test_settings_pack_section_no_auto_reprocess_messaging` | Pack section shows no-auto-reprocess |

### Fixtures Created

| Path | Purpose |
|------|---------|
| `packs/invalid_schema_pack/` | Pack with ghost_signal not in taxonomy; scoring + derivers ref invalid |
| `packs/invalid_schema_pack/pack.json` | Valid manifest |
| `packs/invalid_schema_pack/taxonomy.yaml` | Minimal (funding_raised only) |
| `packs/invalid_schema_pack/scoring.yaml` | References ghost_signal (invalid) |
| `packs/invalid_schema_pack/esl_policy.yaml` | Valid |
| `packs/invalid_schema_pack/derivers.yaml` | References ghost_signal (invalid) |
| `packs/invalid_schema_pack/README.md` | Documents test fixture purpose |

---

## 2. Coverage Impact

### Commands

```bash
# Unit + regression (exclude integration)
pytest tests/ -v -m "not integration"

# Full coverage
pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=75

# Integration only
pytest tests/ -v -m integration --cov=app --cov-report=term-missing

# Issue #172 pack tests only
pytest tests/test_pack_loader.py tests/test_pack_schema_validation.py tests/test_pack_resolver.py tests/test_ui_pack_metadata.py -v
```

### Current Coverage (Before Implementation)

- **Overall:** 91.58% (above 75% fail-under)
- **app/packs/loader.py:** 88% (8 lines missing: path validation, error paths)
- **app/packs/schemas.py:** N/A (module does not exist yet)

### After Implementation (Target)

- **Overall:** >= 75%
- **app/packs/loader.py:** >= 85%
- **app/packs/schemas.py:** >= 85% (new module)

### Modules Touched by Issue #172

| Module | Current | Target | Tests Added |
|--------|---------|--------|-------------|
| app/packs/loader.py | 88% | 85% | Derivers, validation integration |
| app/packs/schemas.py | N/A | 85% | 16 unit tests |
| app/services/pack_resolver.py | 100% | No decrease | 1 integration test |

---

## 3. Failing Tests (Expected Before Implementation)

All 22 new tests fail until production code is updated. This is expected TDD red phase.

| Failure Type | Count | Cause |
|--------------|-------|-------|
| `ModuleNotFoundError: app.packs.schemas` | 16 | schemas.py not implemented |
| `AssertionError: Pack must have derivers attribute` | 1 | `Pack` dataclass has no derivers field |
| `AttributeError: 'Pack' object has no attribute 'derivers'` | 1 | Same |
| `AssertionError: resolve_pack must return None when pack validation fails` | 1 | `resolve_pack` does not catch ValidationError |
| `AssertionError: Settings must show active pack metadata` | 1 | Settings template does not render pack |

### Implementation Order (TDD Green Phase)

1. Create `app/packs/schemas.py` with `ValidationError` and `validate_pack_schema` → 16 schema tests pass
2. Add `derivers` to `Pack`, load `derivers.yaml` in loader → 2 derivers tests pass
3. Call `validate_pack_schema` in `load_pack`, raise on invalid → 2 invalid pack tests pass
4. Catch `ValidationError` in `resolve_pack`, return None → 1 resolver test passes
5. Add pack metadata to settings template + view → 1 UI test passes

---

## 4. Verification Commands

```bash
# Unit + regression
pytest tests/ -v -m "not integration"

# Coverage (fail under 75%)
pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=75

# Integration only
pytest tests/ -v -m integration --cov=app --cov-report=term-missing

# Pack tests only (Issue #172)
pytest tests/test_pack_loader.py tests/test_pack_schema_validation.py tests/test_pack_resolver.py tests/test_ui_pack_metadata.py -v
```

---

## 5. Test Types Summary

| Type | Count | Purpose |
|------|-------|---------|
| **Unit** | 18 | Schema validation, derivers, manifest/taxonomy/scoring/derivers/ESL cross-refs |
| **Regression** | 2 | load_pack invalid pack raises; resolve_pack returns None on invalid |
| **Integration** | 1 | resolve_pack with invalid_schema_pack in DB returns None |
| **UI** | 3 | Settings page shows active pack, version, no-auto-reprocess |

---

## 6. Invariants Tested

| Invariant | Test |
|-----------|------|
| **Pack isolation** | Invalid pack does not load; resolve_pack returns None |
| **Schema validation** | All cross-refs (scoring→taxonomy, derivers→taxonomy, ESL→taxonomy) validated |
| **Invalid pack fails cleanly** | load_pack raises ValidationError with clear message |
| **Admin pack visibility** | Settings shows active pack metadata (Issue #172 acceptance) |

---

## 7. Confidence Assessment

### What Passing Tests Guarantee (After Implementation)

- Pack schema validation rejects invalid configs; valid configs pass
- Loader loads derivers.yaml; Pack has derivers
- Invalid pack raises ValidationError; resolve_pack returns None (graceful fallback)
- Settings page shows active pack metadata

### What Remains Risky

- **Regex DoS:** Deriver patterns not yet validated for length/timeout (ADR-008)
- **Pack version upgrade:** No tests for switching pack version
- **Workspace scoping:** get_default_pack_id not yet workspace-aware

### Follow-Up Tests (Post–Issue #172)

- Regex safety: pattern length, timeout in deriver engine
- Pack version upgrade workflow
- Workspace isolation when active_pack_id wired
