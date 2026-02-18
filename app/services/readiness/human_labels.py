"""Human-readable labels for event types (v2-spec §16, Issue #93)."""

from __future__ import annotations

# Map event_type to display string for UI (Emerging Companies section)
EVENT_TYPE_TO_LABEL: dict[str, str] = {
    "funding_raised": "New funding",
    "job_posted_engineering": "Engineering hiring",
    "job_posted_infra": "Infra/DevOps hiring",
    "headcount_growth": "Headcount growth",
    "launch_major": "Major launch",
    "api_launched": "API launch",
    "ai_feature_launched": "AI feature launch",
    "enterprise_feature": "Enterprise feature",
    "compliance_mentioned": "Compliance pressure",
    "enterprise_customer": "Enterprise customer",
    "regulatory_deadline": "Regulatory deadline",
    "founder_urgency_language": "Founder urgency",
    "revenue_milestone": "Revenue milestone",
    "cto_role_posted": "CTO search",
    "fractional_request": "Fractional help requested",
    "advisor_request": "Advisor help requested",
    "no_cto_detected": "No CTO detected",
    "cto_hired": "CTO hired",
}


def event_type_to_label(event_type: str) -> str:
    """Return human-readable label for event_type. Falls back to formatted type if unknown."""
    if not event_type:
        return "Signal"
    return EVENT_TYPE_TO_LABEL.get(event_type, event_type.replace("_", " ").title())
