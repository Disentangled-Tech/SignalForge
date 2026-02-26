# Deployment: Core Taxonomy and Core Derivers (Issue #285)

When the application includes the Core Signal Taxonomy and Core Deriver Registry (Issue #285), the following deployment requirements apply.

## Required at startup

- **Core taxonomy**: The directory `app/core_taxonomy/` and file `app/core_taxonomy/taxonomy.yaml` must be present and valid. Startup validation in `main.py` will **fail** if the taxonomy is missing or invalid (fail-fast).
- **Core derivers**: The directory `app/core_derivers/` and file `app/core_derivers/derivers.yaml` must be present and valid. Startup validation ensures the derivers reference core taxonomy signal_ids.

## Deriver stage behavior

- The **derive** stage uses **core derivers only** (no pack deriver fallback). If core derivers fail to load (e.g. missing file, malformed YAML, or validation error), the deriver job is **marked failed** and the exception propagates.
- Ensure `app/core_taxonomy/` and `app/core_derivers/` are deployed with the application and their YAML files are readable and valid. Run the test suite (including `tests/test_core_*` and deriver tests) in CI to catch invalid config before deploy.

## References

- Core taxonomy: `app/core_taxonomy/loader.py`
- Core derivers: `app/core_derivers/loader.py`
- Deriver engine: `app/pipeline/deriver_engine.py` (core derivers only; Issue #285 M6)
- Docs: `docs/CORE_VS_PACK_RESPONSIBILITIES.md`, `docs/pack_v2_contract.md`
