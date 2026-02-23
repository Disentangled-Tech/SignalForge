# invalid_schema_pack — Test Fixture (Issue #172)

This pack is intentionally invalid for schema validation tests.

- **scoring.yaml**: references `ghost_signal` which is not in taxonomy.signal_ids
- **derivers.yaml**: references `signal_id: ghost_signal` not in taxonomy

Do not use in production. Used by `tests/test_pack_loader.py` and `tests/test_pack_resolver.py`.
