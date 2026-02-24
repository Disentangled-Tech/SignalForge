# Create PR: Phases 2–4 + Lead Feed + Maintainer Fixes

## 1. Commit and push

```bash
# Stage all changes
git add -A

# Commit (adjust message if needed)
git commit -m "Phases 2–4: CTO pack extraction, pack activation, ESL gate, lead feed, maintainer fixes

- Phase 2: minimum_threshold, disqualifier_signals, evidence_event_ids merge
- Phase 3: workspace_id/pack_id on run_score, run_derive, run_ingest
- Phase 4: ESL decision gate, briefing filters suppressed
- Lead feed: projection table, run_update_lead_feed endpoint
- Code review fixes: migration idempotency, evidence dedup, 422 tests

Closes #174, #175, #173, #225"

# Push branch
git push -u origin feat/issue-174-phase4-cleanup
```

## 2. Create PR

```bash
gh pr create \
  --title "Phases 2–4: CTO Pack Extraction, Pack Activation, ESL Gate + Lead Feed + Maintainer Fixes" \
  --body-file .github/PR_BODY_MAINTAINER_FIXES.md \
  --base main
```

If `gh` auth fails, run `gh auth login` first.

## 3. Alternative: Create via GitHub UI

1. Push the branch (step 1 above).
2. Go to https://github.com/Disentangled-Tech/SignalForge/compare
3. Select base: `main`, compare: `feat/issue-174-phase4-cleanup`
4. Click "Create pull request"
5. Paste contents of `.github/PR_BODY_MAINTAINER_FIXES.md` into the description
