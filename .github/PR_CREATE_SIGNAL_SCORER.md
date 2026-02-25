# Create PR for SignalScorer v0 (Issue #242)

## Option A: Create PR from current branch (includes all changes)

```bash
# Ensure you're on your feature branch with SignalScorer changes
git status

# Push branch (replace BRANCH_NAME with your branch name, e.g. signal-scorer-phase2)
git push -u origin BRANCH_NAME

# Open PR in browser (GitHub will suggest creating a PR after push)
# Or use GitHub CLI:
gh pr create --title "Implement SignalScorer v0 (weights + recommendation bands)" \
  --body-file .github/PR_SIGNAL_SCORER_PHASE2_BODY.md \
  --base main
```

## Option B: Create clean PR (SignalScorer only, exclude NewsAPI)

If you want a PR with only SignalScorer changes:

```bash
# Create a new branch from main
git checkout main
git pull origin main
git checkout -b signal-scorer-242

# Cherry-pick or apply only SignalScorer commits (adjust commit hashes)
# Or: revert the NewsAPI changes, then commit
git revert --no-commit <newsapi_commit_hash>  # if NewsAPI was a single commit

# Push and create PR
git push -u origin signal-scorer-242
gh pr create --title "Implement SignalScorer v0 (weights + recommendation bands)" \
  --body-file .github/PR_SIGNAL_SCORER_PHASE2_BODY.md \
  --base main
```

## PR body

Use the contents of `.github/PR_SIGNAL_SCORER_PHASE2_BODY.md` as the PR description. It already includes `Closes #242` to link and auto-close the issue.
