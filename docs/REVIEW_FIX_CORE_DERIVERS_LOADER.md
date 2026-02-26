# Code review fix: Core derivers loader must pass core signal_ids to validator

**Applies to branch:** `feat/core-taxonomy-deriver-registry-285` (or the PR that introduces Core Taxonomy and Core Deriver Registry). Apply this fix in the worktree that has that branch checked out (this worktree does not contain `app/core_derivers/`).

## Issue

In `app/core_derivers/loader.py`, the diff removes the import of `get_core_signal_ids` from `app.core_taxonomy.loader` and removes the call `validate_core_derivers(derivers, get_core_signal_ids())` from the duplicate block that was deleted. The **remaining** `load_core_derivers()` implementation (inside the `try:` block) must still call the validator with the allowed signal_ids set from the core taxonomy; otherwise validation may be incomplete or the validator may receive no allowed set.

## Required fix

1. **Restore the import** at the top of `app/core_derivers/loader.py`:

   ```python
   from app.core_taxonomy.loader import get_core_signal_ids
   ```

2. **Ensure** that inside `load_core_derivers()`, after loading the YAML data, the validator is called with the core signal_ids:

   ```python
   validate_core_derivers(data, get_core_signal_ids())
   ```

   (Use the actual variable name for the loaded dict in that function—e.g. `data` or `derivers`—and pass it as the first argument; the second argument must be the set or list of allowed signal_ids from `get_core_signal_ids()`.)

## Verification

- Run tests that load and validate core derivers (e.g. `tests/test_core_derivers*.py` or pack schema tests that load a v2 pack).
- Confirm that a core derivers YAML with a `signal_id` not in core taxonomy fails validation with a clear error.
