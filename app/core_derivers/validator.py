"""Core derivers schema validation (Issue #285, Milestone 2).

Validates core derivers YAML:
- Structure: must have 'derivers' key with dict value
- Passthrough entries: must have event_type and signal_id; signal_id must be in core taxonomy
- Pattern entries: must have signal_id and pattern/regex; signal_id must be in core taxonomy;
  source_fields must be in allowed set; regex must be safe (no catastrophic backtracking)

Reuses app.packs.regex_validator for regex safety (ADR-008).
"""

from __future__ import annotations

from typing import Any

from app.packs.regex_validator import validate_deriver_regex_safety
from app.packs.schemas import ALLOWED_PATTERN_SOURCE_FIELDS, ValidationError


class CoreDeriversValidationError(ValueError):
    """Raised when core derivers validation fails.

    Subclasses ValueError so callers can catch it via ``except ValueError``
    alongside ``FileNotFoundError`` without needing to import this class.
    """


def validate_core_derivers(derivers: dict[str, Any]) -> None:
    """Validate core derivers structure, signal_ids against core taxonomy, and regex safety.

    Args:
        derivers: Loaded derivers.yaml content.

    Raises:
        CoreDeriversValidationError: When structural or referential integrity validation fails,
            including when regex safety validation detects dangerous patterns.
    """
    if not isinstance(derivers, dict):
        raise CoreDeriversValidationError("core derivers must be a dict")

    inner = derivers.get("derivers")
    if inner is None:
        raise CoreDeriversValidationError("core derivers must have a 'derivers' key")
    if not isinstance(inner, dict):
        raise CoreDeriversValidationError("core derivers 'derivers' value must be a dict")

    from app.core_taxonomy.loader import get_core_signal_ids

    core_signal_ids = get_core_signal_ids()

    # Validate passthrough derivers
    passthrough = inner.get("passthrough") or []
    if not isinstance(passthrough, list):
        raise CoreDeriversValidationError("core derivers 'passthrough' must be a list")
    for i, entry in enumerate(passthrough):
        if not isinstance(entry, dict):
            raise CoreDeriversValidationError(
                f"core derivers passthrough entry at index {i} must be a dict"
            )
        if "event_type" not in entry:
            raise CoreDeriversValidationError(
                f"core derivers passthrough entry at index {i} missing required field 'event_type'"
            )
        if "signal_id" not in entry:
            raise CoreDeriversValidationError(
                f"core derivers passthrough entry at index {i} missing required field 'signal_id'"
            )
        sid = entry.get("signal_id")
        if sid not in core_signal_ids:
            raise CoreDeriversValidationError(
                f"core derivers passthrough entry at index {i} references signal_id '{sid}' "
                f"not in core taxonomy"
            )

    # Validate pattern derivers
    pattern_list = inner.get("pattern") or []
    if not isinstance(pattern_list, list):
        raise CoreDeriversValidationError("core derivers 'pattern' must be a list")
    for i, entry in enumerate(pattern_list):
        if not isinstance(entry, dict):
            raise CoreDeriversValidationError(
                f"core derivers pattern entry at index {i} must be a dict"
            )
        if "signal_id" not in entry:
            raise CoreDeriversValidationError(
                f"core derivers pattern entry at index {i} missing required field 'signal_id'"
            )
        if "pattern" not in entry and "regex" not in entry:
            raise CoreDeriversValidationError(
                f"core derivers pattern entry at index {i} must have 'pattern' or 'regex'"
            )
        sid = entry.get("signal_id")
        if sid not in core_signal_ids:
            raise CoreDeriversValidationError(
                f"core derivers pattern entry at index {i} references signal_id '{sid}' "
                f"not in core taxonomy"
            )
        source_fields = entry.get("source_fields")
        if source_fields is not None and isinstance(source_fields, list):
            for j, field in enumerate(source_fields):
                if field not in ALLOWED_PATTERN_SOURCE_FIELDS:
                    raise CoreDeriversValidationError(
                        f"core derivers pattern entry at index {i} source_fields[{j}] "
                        f"'{field}' not allowed; must be one of "
                        f"{sorted(ALLOWED_PATTERN_SOURCE_FIELDS)}"
                    )

    # Delegate regex safety validation to the existing pack validator (ADR-008)
    try:
        validate_deriver_regex_safety(derivers)
    except ValidationError as exc:
        raise CoreDeriversValidationError(str(exc)) from exc
