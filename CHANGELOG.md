# Changelog

All notable changes to the SignalForge project are documented here.

## [Unreleased]

### Deprecated

- **bookkeeping_v1 pack (Issue #289):** The bookkeeping_v1 signal pack is deprecated. The pack directory has been removed from the repo. The `signal_packs` row may remain in the database with `is_active=false` for referential integrity (LeadFeed, SignalInstance FKs). For tests, use the `example_v1`, `example_esl_blocked`, or `second_pack` / `esl_blocked_pack_id` fixtures; for production, use fractional role packs (e.g. fractional_cto_v1, fractional_cmo_v1).
