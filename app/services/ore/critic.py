"""ORE critic — rules for draft compliance (Issue #124).

Per docs/critic_rules.md:
- No surveillance phrases
- No urgency language
- Single CTA
- Opt-out language
- Short paragraphs
- Avoid shame framing (M4): core list always enforced; packs may add via forbidden_phrases.
- When tone_constraint provided: draft must not exceed that tier (M4).

Source of truth: RECOMMENDATION_ORDER in this module is the canonical tier order.
esl_gate_filter must import it; do not duplicate. See docs/critic_rules.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.services.ore.suppressed_signal_phrases import get_phrases_for_suppressed_signals

RECOMMENDATION_ORDER: tuple[str, ...] = (
    "Observe Only",
    "Soft Value Share",
    "Low-Pressure Intro",
    "Standard Outreach",
    "Direct Strategic Outreach",
)
_TIER_INDICATOR_PHRASES: dict[str, list[str]] = {
    "Direct Strategic Outreach": [
        "let's schedule a call",
        "book a call",
        "strategic partnership",
        "i'd like to propose",
        "direct ask",
    ],
    "Standard Outreach": [
        "schedule a call",
        "15-min call",
        "hop on a call",
        "quick call",
        "short call",
    ],
    "Low-Pressure Intro": ["intro call", "brief intro"],
}
_SHAME_PATTERNS = [
    re.compile(r"\bfalling behind\b", re.I),
    re.compile(r"\byou must\b", re.I),
    re.compile(r"\byou should\b", re.I),
    re.compile(r"\byou're struggling\b", re.I),
    re.compile(r"\byou need to\b", re.I),
    re.compile(r"\byou have to\b", re.I),
    re.compile(r"\bdon't fall behind\b", re.I),
]


@dataclass
class CriticResult:
    """Result of critic check."""

    passed: bool
    violations: list[str]
    violation_details: list[dict[str, Any]] | None = None


# Surveillance phrases (from critic_rules.md)
_SURVEILLANCE_PATTERNS = [
    re.compile(r"\bI noticed you\b", re.I),
    re.compile(r"\bI saw that you\b", re.I),
    re.compile(r"\bAfter your recent funding\b", re.I),
    re.compile(r"\bYou're hiring\b", re.I),
]

# Urgency phrases
_URGENCY_PATTERNS = [
    re.compile(r"\bASAP\b", re.I),
    re.compile(r"\burgent\b", re.I),
    re.compile(r"\bbefore it's too late\b", re.I),
    re.compile(r"\bquickly\b", re.I),
]

# CTA patterns (consent-based)
_CTA_PATTERNS = [
    re.compile(r"Want me to send", re.I),
    re.compile(r"Open to a", re.I),
    re.compile(r"If helpful", re.I),
    re.compile(r"would it help", re.I),
]


def check_critic(
    subject: str,
    message: str,
    *,
    forbidden_phrases: list[str] | None = None,
    suppressed_signal_ids: set[str] | None = None,
    tone_constraint: str | None = None,
    pack_id: UUID | None = None,
    allowed_signal_labels: list[str] | None = None,
) -> CriticResult:
    """Run critic checks on draft subject and message.

    When forbidden_phrases is provided (e.g. from pack playbook), draft must not
    contain any of those phrases (case-insensitive). When None or empty, only
    core rules apply.

    M2: When suppressed_signal_ids is provided and non-empty, draft must not
    contain reference phrases for those signals (case-insensitive). Violations
    are appended to violations (string) and violation_details (dict with
    violation_type, signal_id, phrase). M4: tone_constraint caps tier; shame framing:
    core patterns always enforced; packs may add via forbidden_phrases (additive).

    Returns:
        CriticResult with passed=False and violations list if any rule fails.
    """
    del pack_id, allowed_signal_labels
    combined = f"{subject} {message}"
    lower_combined = combined.lower()
    violations: list[str] = []
    violation_details: list[dict[str, Any]] = []

    for pat in _SHAME_PATTERNS:
        m = pat.search(combined)
        if m:
            phrase = m.group(0) or pat.pattern
            violations.append(f"Shame framing: {phrase!r}")
            violation_details.append({"violation_type": "shame_framing", "phrase": phrase})

    if forbidden_phrases:
        for phrase in forbidden_phrases:
            if phrase and phrase.lower() in lower_combined:
                violations.append(f"Pack forbidden phrase: {phrase!r}")

    # M2: suppressed-signal mention check
    if suppressed_signal_ids:
        phrase_map = get_phrases_for_suppressed_signals(suppressed_signal_ids)
        for signal_id, phrases in phrase_map.items():
            for phrase in phrases:
                if phrase and phrase.lower() in lower_combined:
                    violations.append(
                        f"Suppressed signal mention: draft references {signal_id!r} (phrase {phrase!r})"
                    )
                    violation_details.append(
                        {
                            "violation_type": "suppressed_signal",
                            "signal_id": signal_id,
                            "phrase": phrase,
                        }
                    )

    if tone_constraint and isinstance(tone_constraint, str) and tone_constraint.strip():
        try:
            allowed_idx = RECOMMENDATION_ORDER.index(tone_constraint.strip())
        except ValueError:
            allowed_idx = -1
        if allowed_idx >= 0:
            for tier in RECOMMENDATION_ORDER[allowed_idx + 1 :]:
                for phrase in _TIER_INDICATOR_PHRASES.get(tier) or []:
                    if phrase and phrase.lower() in lower_combined:
                        violations.append(
                            f"Tone tier exceeded: draft suggests {tier!r} (phrase {phrase!r}); max allowed {tone_constraint!r}"
                        )
                        violation_details.append(
                            {
                                "violation_type": "tone_tier",
                                "tier_detected": tier,
                                "phrase": phrase,
                                "tone_constraint": tone_constraint.strip(),
                            }
                        )

    for p in _SURVEILLANCE_PATTERNS:
        if p.search(combined):
            violations.append(f"Surveillance phrase: {p.pattern}")

    for p in _URGENCY_PATTERNS:
        if p.search(combined):
            violations.append(f"Urgency language: {p.pattern}")

    cta_count = sum(1 for p in _CTA_PATTERNS if p.search(message))
    if cta_count > 1:
        violations.append("Multiple CTAs detected (max 1)")

    # Opt-out: "No worries if now isn't the time" or similar
    opt_out_patterns = [
        re.compile(r"no worries if", re.I),
        re.compile(r"no pressure", re.I),
        re.compile(r"if now isn't the time", re.I),
    ]
    if not any(p.search(combined) for p in opt_out_patterns):
        violations.append("Missing opt-out language")

    return CriticResult(
        passed=len(violations) == 0,
        violations=violations,
        violation_details=violation_details,
    )
