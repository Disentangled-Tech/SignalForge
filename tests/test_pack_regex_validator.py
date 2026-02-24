"""Pack regex safety validation tests (Issue #190, Phase 2, ADR-008).

Tests for validate_deriver_regex_safety: pattern length, catastrophic backtracking,
valid patterns, and passthrough-only derivers (no-op).
"""

from __future__ import annotations

import pytest


def _passthrough_only_derivers() -> dict:
    """Derivers with only passthrough (no regex patterns)."""
    return {
        "derivers": {
            "passthrough": [
                {"event_type": "funding_raised", "signal_id": "funding_raised"},
                {"event_type": "cto_role_posted", "signal_id": "cto_role_posted"},
            ]
        }
    }


class TestRegexValidatorPassthroughOnly:
    """Passthrough-only derivers are a no-op (no regex to validate)."""

    def test_passthrough_only_passes(self) -> None:
        """Derivers with only passthrough entries do not raise."""
        from app.packs.regex_validator import validate_deriver_regex_safety

        validate_deriver_regex_safety(_passthrough_only_derivers())
        # No exception

    def test_empty_derivers_passes(self) -> None:
        """Empty derivers dict does not raise."""
        from app.packs.regex_validator import validate_deriver_regex_safety

        validate_deriver_regex_safety({})
        validate_deriver_regex_safety({"derivers": {}})


class TestRegexValidatorPatternLength:
    """Patterns exceeding MAX_PATTERN_LENGTH are rejected."""

    def test_pattern_too_long_raises(self) -> None:
        """Pattern longer than MAX_PATTERN_LENGTH raises ValidationError."""
        from app.packs.regex_validator import MAX_PATTERN_LENGTH, validate_deriver_regex_safety
        from app.packs.schemas import ValidationError

        long_pattern = "a" * (MAX_PATTERN_LENGTH + 1)
        derivers = {
            "derivers": {
                "pattern": [{"pattern": long_pattern, "signal_id": "test_signal"}]
            }
        }
        with pytest.raises(ValidationError, match="exceeds maximum|length|500"):
            validate_deriver_regex_safety(derivers)

    def test_pattern_at_limit_passes(self) -> None:
        """Pattern at exactly MAX_PATTERN_LENGTH passes (if otherwise safe)."""
        from app.packs.regex_validator import (
            MAX_PATTERN_LENGTH,
            validate_deriver_regex_safety,
        )

        pattern = r"\bfunding\b" + "x" * (MAX_PATTERN_LENGTH - 12)  # 12 + 488 = 500
        derivers = {
            "derivers": {
                "pattern": [{"pattern": pattern, "signal_id": "funding_raised"}]
            }
        }
        validate_deriver_regex_safety(derivers)


class TestRegexValidatorDangerousPatterns:
    """Patterns with catastrophic backtracking constructs are rejected."""

    def test_nested_quantifiers_raises(self) -> None:
        """Pattern with (.*)+ or similar nested quantifiers raises."""
        from app.packs.regex_validator import validate_deriver_regex_safety
        from app.packs.schemas import ValidationError

        dangerous = [
            r"(.*)+",
            r"(.+)*",
            r"(\w+)*",
            r"(\s+)+",
        ]
        for pat in dangerous:
            derivers = {
                "derivers": {"pattern": [{"pattern": pat, "signal_id": "x"}]}
            }
            with pytest.raises(ValidationError, match="catastrophic|backtracking|unsafe"):
                validate_deriver_regex_safety(derivers)

    def test_valid_simple_pattern_passes(self) -> None:
        """Simple safe patterns pass."""
        from app.packs.regex_validator import validate_deriver_regex_safety

        safe_patterns = [
            r"\bfunding\b",
            r"cto_role_posted",
            r"^job_posted_\w+$",
            r"[A-Z]{2,4}",  # ticker-like
        ]
        for pat in safe_patterns:
            derivers = {
                "derivers": {"pattern": [{"pattern": pat, "signal_id": "test"}]}
            }
            validate_deriver_regex_safety(derivers)


class TestRegexValidatorStructure:
    """Validator handles various deriver structures."""

    def test_regex_key_also_validated(self) -> None:
        """Entries with 'regex' key (alias for pattern) are validated."""
        from app.packs.regex_validator import validate_deriver_regex_safety
        from app.packs.schemas import ValidationError

        derivers = {
            "derivers": {"pattern": [{"regex": r"(.*)+", "signal_id": "x"}]}
        }
        with pytest.raises(ValidationError):
            validate_deriver_regex_safety(derivers)

    def test_invalid_regex_syntax_raises(self) -> None:
        """Malformed regex (unclosed paren, etc.) raises ValidationError."""
        from app.packs.regex_validator import validate_deriver_regex_safety
        from app.packs.schemas import ValidationError

        derivers = {
            "derivers": {"pattern": [{"pattern": r"(unclosed", "signal_id": "x"}]}
        }
        with pytest.raises(ValidationError, match="invalid|syntax|regex"):
            validate_deriver_regex_safety(derivers)
