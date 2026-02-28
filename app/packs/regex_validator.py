"""Regex safety validation for pack derivers (ADR-008, Issue #190, Phase 2).

Validates deriver patterns for length and catastrophic backtracking risk.
Passthrough derivers (no pattern/regex) are a no-op.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["MAX_PATTERN_LENGTH", "validate_deriver_regex_safety"]

# Maximum allowed pattern length (ADR-008)
MAX_PATTERN_LENGTH = 500

# Substrings indicating catastrophic backtracking risk (ReDoS)
# Nested quantifiers: (X+)+, (X*)*, (X+)*, (X*)+ where X is ., \w, \s, \d
_DANGEROUS_PATTERNS = (
    r"(.+)+",
    r"(.*)+",
    r"(.+)*",
    r"(.*)*",
    r"(\w+)+",
    r"(\w+)*",
    r"(\w*)+",
    r"(\w*)*",
    r"(\s+)+",
    r"(\s+)*",
    r"(\s*)+",
    r"(\s*)*",
    r"(\d+)+",
    r"(\d+)*",
    r"(\d*)+",
    r"(\d*)*",
)


def _collect_pattern_strings(obj: Any, patterns: list[tuple[str, str]]) -> None:
    """Recursively collect pattern/regex strings from derivers structure."""
    if isinstance(obj, dict):
        for key in ("pattern", "regex"):
            if key in obj and isinstance(obj[key], str):
                patterns.append((key, obj[key]))
        for v in obj.values():
            _collect_pattern_strings(v, patterns)
    elif isinstance(obj, list):
        for item in obj:
            _collect_pattern_strings(item, patterns)


def validate_deriver_regex_safety(derivers: dict[str, Any]) -> None:
    """Validate deriver patterns for length and ReDoS safety.

    Passthrough derivers (no pattern/regex) are skipped. For any entry with
    'pattern' or 'regex' key, validates: max length, no catastrophic
    backtracking constructs, valid regex syntax.

    Args:
        derivers: derivers.yaml content (e.g. {"derivers": {"passthrough": [...]}}).

    Raises:
        ValidationError: When a pattern exceeds max length, contains dangerous
            constructs, or has invalid regex syntax.
    """
    from app.packs.schemas import ValidationError

    if not isinstance(derivers, dict):
        return

    patterns: list[tuple[str, str]] = []
    _collect_pattern_strings(derivers, patterns)

    for key, pat in patterns:
        if len(pat) > MAX_PATTERN_LENGTH:
            raise ValidationError(
                f"deriver {key} pattern length {len(pat)} exceeds maximum "
                f"{MAX_PATTERN_LENGTH} (ADR-008)"
            )

        for dangerous in _DANGEROUS_PATTERNS:
            if dangerous in pat:
                raise ValidationError(
                    f"deriver {key} contains unsafe regex (catastrophic backtracking risk): "
                    f"'{dangerous}' is not allowed (ADR-008)"
                )

        try:
            re.compile(pat)
        except re.error as e:
            raise ValidationError(f"deriver {key} has invalid regex syntax: {e}") from e
