# Explanation Generator (Issue #18)

Generate "why this company likely needs CTO help" — 2–6 sentences, not generic startup advice.

## Rules

- Use only evidence from stage, pain signals, and evidence bullets.
- Do NOT give generic startup advice.
- Be specific to THIS company. Cite concrete signals.
- Write 2–6 sentences.
- If evidence is weak, say so briefly rather than filling with platitudes.

## Inputs

- COMPANY_NAME
- STAGE
- EVIDENCE_BULLETS
- PAIN_SIGNALS_SUMMARY (active signals with value=true and their "why")
- TOP_RISKS (from pain_data)
- MOST_LIKELY_NEXT_PROBLEM (from pain_data)
