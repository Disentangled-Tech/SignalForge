# Implementation Plan: GitHub Issue #19 — Outreach Message Generator

**Issue**: [Outreach message generator](https://github.com/Disentangled-Tech/SignalForge/issues/19)  
**Constraints**: <140 words, conversational, no marketing tone  
**Acceptance Criteria**: Reads human, mentions company context, no hallucinated claims

---

## Summary of Changes

### 1. Prompt Strengthening (`app/prompts/outreach_v1.md`, `rules/outreach_v1.md`)

- Added explicit "conversational tone" and "no marketing tone" per Issue #19
- Added "Reference at least one specific detail about this company" for company context AC
- Added STRICT 140-word instruction

### 2. Word-Count Enforcement (`app/services/outreach.py`)

- Retry once when message exceeds 140 words (PRD: regenerate once on violation)
- If retry still over 140 words: truncate with `_truncate_to_word_limit()` preferring sentence boundaries
- New helper `_truncate_to_word_limit()` for truncation logic

### 3. Company Detail Page Copy (`app/templates/companies/detail.html`)

- "Run a daily briefing or rescan to generate one" → "Run a daily briefing to generate an outreach draft."
- Rescan does not generate outreach; only the daily briefing does.

### 4. Tests

- `test_word_count_over_140_triggers_retry`
- `test_word_count_retry_still_over_truncates`
- `test_word_count_under_140_no_retry`
- `TestTruncateToWordLimit` (unit tests for truncation)
- `test_outreach_v1_includes_issue_19_acceptance_criteria` (prompt content)
- Updated view tests to assert "daily briefing" in empty-state message

---

## Verification

- [x] All outreach, prompts, hallucination, briefing, analysis, scoring tests pass
- [x] Snyk scan on `app/services/outreach.py`: 0 issues
- [x] No schema changes; no breaking changes
