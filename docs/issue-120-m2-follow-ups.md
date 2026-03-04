# Issue #120 — Pack-aware safety critic: follow-ups after M2

M2 (critic context and suppressed-signal check) is implemented. Remaining milestones from the plan:

- **M3 — Pipeline wiring and logging:** Wire pipeline to compute no_reference set from pack + core, pass `suppressed_signal_ids` (and optionally `pack_id`) into `check_critic`; on critic failure set `strategy_notes` and log violation type, pack_id, signal_id (structured).
- **M6 — Documentation and cleanup:** Update ORE design spec, critic_rules, playbook-draft-engine, and CORE_BAN_SIGNAL_IDS.md to note that the critic blocks draft mentions of core-banned and pack-blocked signals when `suppressed_signal_ids` is supplied.

These are tracked as follow-ups and do not block M2 merge.
