Review the proposed changes as if you're the maintainer of a live SaaS product.

Your job:
- Identify scope creep
- Identify behavior changes
- Identify security/multi-tenant risks
- Identify pack isolation violations
- Identify data migration risks
- Identify performance risks (joins, missing indexes, N+1)
- Identify tests missing for regression protection

Checklist:
1) Backward compatibility:
   - Does fractional CTO behavior remain identical?
   - Any renames or changed defaults that could alter outcomes?
2) Pack scoping:
   - Are workspace_id AND pack_id enforced everywhere they must be?
   - Any query that could leak data across tenant or pack?
3) ESL & safety:
   - Are core hard bans still enforced?
   - Can pack config bypass restrictions?
4) Pipeline correctness:
   - Any job idempotency risks (duplicates, double scoring)?
   - Any race conditions in lead feed projection updates?
5) Data migrations:
   - Are migrations additive and reversible?
   - Are NOT NULL constraints added only after backfill?
6) Performance:
   - Any new hot-path joins?
   - Are indexes added for new query patterns?
7) Tests:
   - What exact tests cover this change?
   - What new tests should be added?
8) Documentation:
   - Are ADR assumptions respected?
   - Any TODOs that need tracking?

Output format:
- Safe to merge / Not safe to merge. If there are critical issues, the work is not safe to merge.
- Top 5 critical issues (if any)
- Required fixes before merge
- Suggested follow-ups (nice-to-haves)
Do not propose rewrites. Be concrete and specific.
