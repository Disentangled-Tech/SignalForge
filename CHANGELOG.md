# Changelog

All notable changes to the SignalForge project are documented here.

## [Unreleased]

### Added

- **Watchlist Seeder documentation (Issue #279 M5):** [docs/watchlist_seeder.md](docs/watchlist_seeder.md) — Describes input (bundle_ids from evidence store), flow (register entities → persist Core Events → derive → score), dedupe (source_event_id), and that pack selection affects scoring only.

### Changed

- **Deriver engine cleanup (Issue #279 M5):** Removed dead/duplicate code in `app/pipeline/deriver_engine.py`: the erroneous first `_load_core_derivers` block (pack-based, wrong return type) and the unused `_build_passthrough_map(pack)`. Derive continues to use the single correct implementation that loads core derivers via `get_core_passthrough_map` and `get_core_pattern_derivers`.

### Deprecated

- **bookkeeping_v1 pack (Issue #289):** The bookkeeping_v1 signal pack is deprecated. The pack directory has been removed from the repo. The `signal_packs` row may remain in the database with `is_active=false` for referential integrity (LeadFeed, SignalInstance FKs). For tests, use the `example_v1`, `example_esl_blocked`, or `second_pack` / `esl_blocked_pack_id` fixtures; for production, use fractional role packs (e.g. fractional_cto_v1, fractional_cmo_v1).
