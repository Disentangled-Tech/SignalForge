"""Core ethical constants and validation (ADR-006, Issue #190).

Core enforces non-overridable bans. Pack ESL policies can only further restrict
behavior, not loosen core bans. Packs that attempt to override these bans fail
validation.
"""

from __future__ import annotations

from typing import Any

# Keys that, if present and truthy in esl_policy, indicate pack attempts to
# override core bans. ADR-006: protected attribute inference, bankruptcy/tax
# lien exploitation, targeting vulnerability states, high-sensitivity distress.
CORE_HARD_BAN_KEYS: frozenset[str] = frozenset({
    "allow_protected_attribute_targeting",
    "allow_protected_attribute_inference",
    "allow_bankruptcy_exploitation",
    "allow_tax_lien_exploitation",
    "allow_vulnerability_targeting",
    "allow_distress_surfacing",
    "allow_high_sensitivity_distress",
})

# Protected attribute categories that packs must never target (reference only).
PROTECTED_ATTRIBUTE_CATEGORIES: frozenset[str] = frozenset({
    "race",
    "ethnicity",
    "religion",
    "gender",
    "sexual_orientation",
    "age",
    "disability",
    "national_origin",
})


def validate_esl_policy_against_core_bans(esl_policy: dict[str, Any]) -> None:
    """Reject esl_policy if it attempts to override core ethical bans.

    Pack ESL policies can only further restrict behavior. Any key in
    CORE_HARD_BAN_KEYS that is present and truthy causes ValidationError.

    Args:
        esl_policy: esl_policy.yaml content.

    Raises:
        ValidationError: When pack attempts to allow banned behavior.
    """
    from app.packs.schemas import ValidationError

    if not isinstance(esl_policy, dict):
        return

    for key in CORE_HARD_BAN_KEYS:
        val = esl_policy.get(key)
        if val in (True, 1) or (
            isinstance(val, str) and val.lower() in ("true", "yes", "1", "on", "enable")
        ):
            raise ValidationError(
                f"esl_policy cannot override core ban: '{key}' is not allowed. "
                "Pack policies can only further restrict behavior (ADR-006)."
            )
