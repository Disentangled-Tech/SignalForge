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
from typing import Any
from uuid import UUID

from app.services.ore.suppressed_signal_phrases import get_phrases_for_suppressed_signals


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
    violation_type, signal_id, phrase). tone_constraint, pack_id,
    allowed_signal_labels are accepted for pipeline wiring; tone-tier check in M4.

    Returns:
        CriticResult with passed=False and violations list if any rule fails.
    """
    del tone_constraint, pack_id, allowed_signal_labels  # M4: tone check; logging uses pack_id
    combined = f"{subject} {message}"
    lower_combined = combined.lower()
    violations: list[str] = []
    violation_details: list[dict[str, Any]] = []

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
