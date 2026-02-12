You are diagnosing whether a company is likely to need fractional CTO / engineering leadership help soon.

Rules:
- Use only evidence from signals text.
- Do not invent details.
- Produce structured flags AND short, concrete reasoning.
- If uncertain, set the flag false and note it in "uncertainties".

Return ONLY valid JSON matching this schema:

{
  "signals": {
    "hiring_engineers": { "value": true|false, "why": "string" },
    "switching_from_agency": { "value": true|false, "why": "string" },
    "adding_enterprise_features": { "value": true|false, "why": "string" },
    "compliance_security_pressure": { "value": true|false, "why": "string" },
    "product_delivery_issues": { "value": true|false, "why": "string" },
    "architecture_scaling_risk": { "value": true|false, "why": "string" },
    "founder_overload": { "value": true|false, "why": "string" }
  },
  "top_risks": ["string", "string", "string"],
  "most_likely_next_problem": "string",
  "uncertainties": ["string", "string"],
  "recommended_conversation_angle": "string"
}

Interpretation guide (examples):
- hiring_engineers: job posts for SWE/DevOps/data; “we’re growing the engineering team”
- switching_from_agency: mentions agency, contractors, “bringing in-house”
- adding_enterprise_features: SSO, RBAC, audit logs, SLAs, uptime, multi-tenant, integrations demanded by bigger customers
- compliance_security_pressure: SOC2, HIPAA, ISO, vendor security questionnaires, pentests
- product_delivery_issues: missed timelines, “slipping”, “hard to ship”, bug volume, rebuilds
- architecture_scaling_risk: rewrites, performance bottlenecks, reliability issues, “outgrowing” stack
- founder_overload: burnout posts, “wearing too many hats”, looking for technical leadership

Inputs:
Company:
- Name: {{COMPANY_NAME}}
- Website: {{WEBSITE_URL}}
- Founder: {{FOUNDER_NAME}}
- Notes: {{COMPANY_NOTES}}

Signals text:
{{SIGNALS_TEXT}}
