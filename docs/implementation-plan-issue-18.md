# Implementation Plan: GitHub Issue #18 — Explanation Generator

**Issue**: [Explanation generator](https://github.com/Disentangled-Tech/SignalForge/issues/18)  
**Acceptance Criteria**:
- Generate: "why this company likely needs CTO help"
- 2–6 sentence explanation
- Not generic startup advice

---

## Architecture Context (CURSOR_PRD.md)

The PRD identifies three most important outputs:
1. Correct company stage classification
2. **Clear explanation of "why now"**
3. A believable human outreach draft

The Analysis Pipeline (PRD § Analysis Pipeline) specifies:
1. Stage classification
2. Pain signal detection
3. **Explanation generation**
4. Outreach draft generation

**LLM Usage** (PRD § Architectural Rules): The LLM may "generate explanations."

**Prompt Handling** (PRD § Prompt Handling): All prompts must live in `/app/prompts/`; never hardcode prompts in Python; prompts must be versioned by filename.

---

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| Explanation generation | **Implemented** (inline prompt) | `app/services/analysis.py` lines 165–177 |
| Explanation storage | `AnalysisRecord.explanation` | `app/models/analysis_record.py` |
| Explanation display | Company detail page | `app/templates/companies/detail.html` |
| Dedicated prompt file | **Missing** | N/A — prompt is hardcoded in Python |
| AC: 2–6 sentences | **Partial** — prompt says "2-6 sentences" | `app/services/analysis.py` |
| AC: Not generic | **Gap** — no explicit anti-generic guidance | `app/services/analysis.py` |

### Current Implementation (analysis.py)

```python
# ── Explanation generation ────────────────────────────────────────
signal_summary = json.dumps(
    {k: v for k, v in pain_data.get("signals", {}).items() if isinstance(v, dict) and v.get("value")},
    indent=2,
) if pain_data.get("signals") else "{}"

explanation_prompt = (
    f"Based on stage '{stage}' and signals {signal_summary}, "
    "write 2-6 sentences explaining why this company likely needs "
    "technical leadership help. Be specific and cite evidence."
)
explanation = llm.complete(explanation_prompt, temperature=0.7)
```

---

## Gap Analysis

### Issue #18 Requirements vs Current Implementation

| Requirement | Current State | Gap |
|-------------|---------------|-----|
| **Generate "why this company likely needs CTO help"** | Implemented | ✅ No gap |
| **2–6 sentence explanation** | Prompt says "2-6 sentences" | ⚠️ **Partial** — no validation or retry if LLM returns too short/long |
| **Not generic startup advice** | No explicit anti-generic guidance in prompt | ❌ **Gap** — prompt does not forbid generic advice |
| **Prompt in /app/prompts/** | Hardcoded in Python | ❌ **Gap** — violates PRD § Prompt Handling |

### PRD Compliance

| PRD Rule | Current | Required |
|----------|---------|----------|
| Prompts in `/app/prompts/` | Inline in `analysis.py` | Dedicated `explanation_v1.md` |
| Never hardcode prompts | Violated | Use `render_prompt("explanation_v1", ...)` |
| Prompts versioned by filename | N/A | `explanation_v1.md` |

---

## Implementation Tasks

### 1. Create Dedicated Explanation Prompt Template

**Goal**: Move explanation prompt to `/app/prompts/explanation_v1.md` per PRD.

**File**: `app/prompts/explanation_v1.md`

**Content** (draft):

```markdown
You are explaining why a specific company likely needs fractional CTO / technical leadership help.

Rules:
- Use only evidence from the provided stage, pain signals, and evidence bullets.
- Do NOT give generic startup advice (e.g. "startups often need technical leadership").
- Be specific to THIS company. Cite concrete signals.
- Write 2–6 sentences. No more, no less.
- If evidence is weak, say so briefly rather than filling with platitudes.

Output: Plain text only. No JSON, no bullets, no headers.

Inputs:
Company: {{COMPANY_NAME}}
Stage: {{STAGE}}
Evidence bullets:
{{EVIDENCE_BULLETS}}

Active pain signals (value=true) with reasoning:
{{PAIN_SIGNALS_SUMMARY}}

Top risks from analysis: {{TOP_RISKS}}
Most likely next problem: {{MOST_LIKELY_NEXT_PROBLEM}}
```

**Placeholders**:
- `COMPANY_NAME`
- `STAGE`
- `EVIDENCE_BULLETS` — newline-separated or formatted list
- `PAIN_SIGNALS_SUMMARY` — JSON or formatted string of active signals with `why`
- `TOP_RISKS` — from pain_data
- `MOST_LIKELY_NEXT_PROBLEM` — from pain_data

### 2. Update `app/services/analysis.py`

**Goal**: Replace inline prompt with `render_prompt("explanation_v1", ...)`.

**Changes**:
1. Build `evidence_text` from `evidence_bullets` (same pattern as briefing).
2. Build `pain_signals_summary` from active pain signals (value=true) with their `why` strings.
3. Extract `top_risks` and `most_likely_next_problem` from `pain_data`.
4. Call `render_prompt("explanation_v1", ...)` with all placeholders.
5. Call `llm.complete(explanation_prompt, temperature=0.7)` (unchanged).

**Backward compatibility**: If `pain_data` lacks `top_risks` or `most_likely_next_problem`, pass empty string. Existing analysis records are unaffected; only new analyses use the new prompt.

### 3. Add Rules File (Optional but Recommended)

**Goal**: Document explanation rules for maintainers, matching other prompts.

**File**: `rules/explanation_v1.md` — copy of prompt or summary for human reference (same pattern as `rules/pain_signals_v1.md`, `rules/stage_classification_v1.md`).

### 4. Tests (TDD)

**File**: `tests/test_analysis.py`

**New/updated tests**:
1. **`test_explanation_uses_prompt_template`** — Assert `render_prompt` is called with `"explanation_v1"` and correct placeholders (COMPANY_NAME, STAGE, EVIDENCE_BULLETS, PAIN_SIGNALS_SUMMARY, TOP_RISKS, MOST_LIKELY_NEXT_PROBLEM).
2. **`test_explanation_includes_anti_generic_guidance`** — Load `explanation_v1.md` and assert it contains "generic" or "specific" or equivalent anti-generic wording.
3. **`test_explanation_includes_2_6_sentences`** — Load prompt and assert it mentions "2" and "6" (or "2–6") for sentence count.
4. **`test_explanation_prompt_placeholders_filled`** — When `pain_data` has empty `top_risks`/`most_likely_next_problem`, ensure no `{{...}}` remain in rendered prompt (or that placeholders get empty string).

**Existing tests to verify**:
- `test_returns_analysis_record` — still passes; explanation still stored.
- `test_explanation_uses_temperature_07` — update mock to expect `render_prompt` for explanation (third LLM call still uses temp 0.7).

### 5. Validation (Optional Enhancement)

**Goal**: If explanation is too short (< 2 sentences) or too long (> 6 sentences), optionally retry or truncate.

**Recommendation**: Defer to a follow-up. The prompt instruction is sufficient for V1. Adding sentence-count validation adds complexity and may reject valid edge cases (e.g. 1 long sentence that conveys the idea). Focus on prompt quality first.

---

## Data Flow (No Schema Changes)

```
Company + Signals
    → Stage classification (stage_classification_v1)
    → Pain signal detection (pain_signals_v1)
    → Explanation generation (explanation_v1)  ← NEW: use template
    → AnalysisRecord.explanation
```

**No migrations.** `AnalysisRecord.explanation` already exists. Briefing pipeline uses `why_now` from `briefing_entry_v1`, not `analysis.explanation`; both remain. Company detail page displays `analysis.explanation`; no template change needed.

---

## Verification Checklist

- [ ] Prompt file `app/prompts/explanation_v1.md` exists with anti-generic and 2–6 sentence rules.
- [ ] `analysis.py` uses `render_prompt("explanation_v1", ...)` instead of inline prompt.
- [ ] All placeholders (COMPANY_NAME, STAGE, EVIDENCE_BULLETS, PAIN_SIGNALS_SUMMARY, TOP_RISKS, MOST_LIKELY_NEXT_PROBLEM) are filled.
- [ ] Existing tests pass; new tests for explanation prompt added.
- [ ] No schema changes; no breaking changes to API or UI.
- [ ] Snyk scan on modified code per project rules.

---

## Summary

| Task | Effort | Risk |
|------|--------|------|
| Create `explanation_v1.md` prompt | Low | None |
| Update `analysis.py` to use template | Low | Low |
| Add `rules/explanation_v1.md` | Low | None |
| Add/update tests | Low | None |

**Total**: ~1–2 hours. No schema changes. No breaking changes. Satisfies Issue #18 AC and PRD prompt rules.
