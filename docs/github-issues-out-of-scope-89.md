# GitHub Issues: Out of Scope (Issue #89)

These issues were extracted from the [Ingestion Adapter Framework plan](.cursor/plans/issue_89_ingestion_adapter_framework_d9cb0fe8.plan.md) Section 8. Create each issue in the SignalForge repo.

---

## Issue 1: Real Crunchbase/Product Hunt Adapters

**Title:** Implement Crunchbase and Product Hunt ingestion adapters

**Labels:** `enhancement`, `ingestion`, `adapter`

**Body:**

```markdown
## Summary

Implement real adapters for Crunchbase and Product Hunt that conform to the `SourceAdapter` interface defined in Issue #89.

## Context

Issue #89 establishes the ingestion adapter framework with:
- `SourceAdapter` abstract base class
- `RawEvent` schema
- Normalization, company resolution, and deduplication pipeline

The framework includes a `TestAdapter` for integration testing. This issue covers production adapters for external signal sources.

## Requirements

- [ ] **Crunchbase adapter**: Implement `SourceAdapter` that fetches events from Crunchbase API (or scraping if API unavailable)
- [ ] **Product Hunt adapter**: Implement `SourceAdapter` that fetches events from Product Hunt API
- [ ] Both adapters return `RawEvent` instances with valid `event_type_candidate`, `source_event_id`, and company info
- [ ] Handle rate limiting and pagination appropriately
- [ ] Document API keys/credentials required (if any)

## References

- Issue #89 (Ingestion Adapter Framework)
- [docs/adapter-interface.md](docs/adapter-interface.md) — adapter contract and RawEvent schema
```

---

## Issue 2: POST /internal/run_ingest Endpoint

**Title:** Add POST /internal/run_ingest endpoint for ingestion

**Labels:** `enhancement`, `ingestion`, `api`

**Body:**

```markdown
## Summary

Add an internal API endpoint to trigger the ingestion pipeline programmatically.

## Context

Issue #89 implements the ingestion orchestrator (`run_ingest`) that can be invoked via script or cron. This issue adds an HTTP endpoint for triggering ingestion, e.g. from CI/CD or internal tooling.

## Requirements

- [ ] Add `POST /internal/run_ingest` endpoint
- [ ] Accept optional query params: `adapter` (source name), `since` (ISO datetime)
- [ ] Return ingestion summary: `{inserted, skipped_duplicate, skipped_invalid, errors}`
- [ ] Protect with internal auth (API key or similar)
- [ ] Document in API docs

## References

- Issue #89 (Ingestion Adapter Framework)
- Existing internal endpoints pattern in the codebase
```

---

## Issue 3: Hourly Cron Job for Ingestion

**Title:** Set up hourly cron job for signal ingestion

**Labels:** `enhancement`, `ingestion`, `infrastructure`

**Body:**

```markdown
## Summary

Configure an hourly cron job (or equivalent scheduler) to run the ingestion pipeline for all configured adapters.

## Context

Issue #89 implements `run_ingest` which fetches events from adapters since a given datetime. This issue covers scheduling that run on a regular interval (e.g. hourly).

## Requirements

- [ ] Define cron/scheduler configuration (e.g. Kubernetes CronJob, system cron, or cloud scheduler)
- [ ] Run `run_ingest` for each configured adapter with `since` = last run time (or last N hours)
- [ ] Persist last-run timestamp for each adapter
- [ ] Log results and alert on failures
- [ ] Document deployment and configuration

## References

- Issue #89 (Ingestion Adapter Framework)
- Deployment/infrastructure docs
```

---

## Issue 4: Alert Scan

**Title:** Implement alert scan for signal events

**Labels:** `enhancement`, `ingestion`, `readiness`

**Body:**

```markdown
## Summary

Implement an "alert scan" that processes ingested signal events and triggers appropriate alerts or notifications.

## Context

The ingestion framework (Issue #89) stores `SignalEvent` rows that feed the readiness engine. This issue covers scanning those events and generating alerts (e.g. for high-priority events, threshold breaches, or new company signals).

## Requirements

- [ ] Define alert scan logic (what events trigger alerts)
- [ ] Integrate with notification channels (email, Slack, etc.)
- [ ] Respect user/company preferences for alert frequency and types
- [ ] Design for privacy and security (no PII leakage, rate limits)
- [ ] Add tests

## References

- Issue #89 (Ingestion Adapter Framework)
- Readiness engine and SignalEvent model
```

---

## Creating Issues via GitHub CLI

After running `gh auth login` to authenticate, you can create each issue:

```bash
# Issue 1: Crunchbase/Product Hunt adapters
gh issue create --title "Implement Crunchbase and Product Hunt ingestion adapters" \
  --body-file - <<'EOF'
<paste Issue 1 body from above>
EOF

# Issue 2: run_ingest endpoint
gh issue create --title "Add POST /internal/run_ingest endpoint for ingestion" \
  --body-file - <<'EOF'
<paste Issue 2 body from above>
EOF

# Issue 3: Hourly cron
gh issue create --title "Set up hourly cron job for signal ingestion" \
  --body-file - <<'EOF'
<paste Issue 3 body from above>
EOF

# Issue 4: Alert scan
gh issue create --title "Implement alert scan for signal events" \
  --body-file - <<'EOF'
<paste Issue 4 body from above>
EOF
```

Or create them manually at: https://github.com/Disentangled-Tech/SignalForge/issues/new
