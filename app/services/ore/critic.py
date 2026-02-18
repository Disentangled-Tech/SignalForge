"""ORE critic — rules for draft compliance (Issue #124).

Per docs/critic_rules.md:
- No surveillance phrases
- No urgency language
- Single CTA
- Opt-out language
- Short paragraphs
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CriticResult:
    """Result of critic check."""

    passed: bool
    violations: list[str]


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


def check_critic(subject: str, message: str) -> CriticResult:
    """Run critic checks on draft subject and message.

    Returns:
        CriticResult with passed=False and violations list if any rule fails.
    """
    combined = f"{subject} {message}"
    violations: list[str] = []

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
    )
