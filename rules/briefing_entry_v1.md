You are generating a daily briefing entry for a single-user dashboard. The user needs clarity and specific reasons.

Rules:
- Be concise but concrete.
- No generic advice.
- Tie reasoning to evidence bullets.
- If uncertain, say so.

Return ONLY valid JSON:

{
  "why_now": "string (2-5 sentences)",
  "risk_summary": "string (1-2 sentences)",
  "suggested_angle": "string (1 sentence)",
  "next_step": "string (1 sentence)"
}

Inputs:
Company:
- {{COMPANY_NAME}} (Founder: {{FOUNDER_NAME}})
- Website: {{WEBSITE_URL}}

Stage: {{STAGE}} (confidence {{STAGE_CONFIDENCE}})

Pain signals:
{{PAIN_SIGNALS_JSON}}

Evidence bullets:
{{EVIDENCE_BULLETS}}
