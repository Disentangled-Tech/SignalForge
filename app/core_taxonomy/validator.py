"""Core taxonomy schema validation (Issue #285, Milestone 1).

Validates that core taxonomy.yaml has the required structure:
- signal_ids: non-empty list of unique strings
- dimensions (optional): dict of dimension_key -> list of signal_ids (must reference signal_ids)
- signals (optional, Issue #148 M1): dict of signal_id -> { sensitivity?: "low"|"medium"|"high" };
  every key must be in signal_ids; sensitivity if present must be one of low, medium, high.
"""

from __future__ import annotations

from typing import Any

ALLOWED_SENSITIVITY = frozenset({"low", "medium", "high"})


class CoreTaxonomyValidationError(ValueError):
    """Raised when core taxonomy validation fails.

    Subclasses ValueError so callers can catch it via ``except ValueError``
    alongside ``FileNotFoundError`` without needing to import this class.
    """


def _validate_signals(taxonomy: dict[str, Any], signal_id_set: set[str]) -> None:
    """Validate optional 'signals' map if present.

    signals: optional dict of signal_id -> { sensitivity?: "low"|"medium"|"high" }.
    Every key must be in signal_ids; each value must be a dict; sensitivity if
    present must be one of low, medium, high.
    """
    signals = taxonomy.get("signals")
    if signals is None:
        return
    if not isinstance(signals, dict):
        raise CoreTaxonomyValidationError("core taxonomy 'signals' must be a dict")
    for signal_id, entry in signals.items():
        if signal_id not in signal_id_set:
            raise CoreTaxonomyValidationError(
                f"core taxonomy signals key '{signal_id}' is not in signal_ids"
            )
        if not isinstance(entry, dict):
            raise CoreTaxonomyValidationError(
                "core taxonomy signals entry for each signal_id must be a dict"
            )
        sens = entry.get("sensitivity")
        if sens is not None:
            if sens not in ALLOWED_SENSITIVITY:
                raise CoreTaxonomyValidationError(
                    f"core taxonomy sensitivity must be one of low, medium, high; got {sens!r}"
                )


def validate_core_taxonomy(taxonomy: dict[str, Any]) -> None:
    """Validate core taxonomy structure.

    Args:
        taxonomy: Loaded taxonomy.yaml content.

    Raises:
        CoreTaxonomyValidationError: When structure or referential integrity fails.
    """
    if not isinstance(taxonomy, dict):
        raise CoreTaxonomyValidationError("core taxonomy must be a dict")

    signal_ids = taxonomy.get("signal_ids")
    if signal_ids is None:
        raise CoreTaxonomyValidationError("core taxonomy must have 'signal_ids'")
    if not isinstance(signal_ids, list):
        raise CoreTaxonomyValidationError("core taxonomy 'signal_ids' must be a list")
    if len(signal_ids) == 0:
        raise CoreTaxonomyValidationError("core taxonomy 'signal_ids' must not be empty")

    signal_id_set: set[str] = set()
    for s in signal_ids:
        if s is None or not isinstance(s, str) or not s.strip():
            raise CoreTaxonomyValidationError(
                f"core taxonomy 'signal_ids' entries must be non-empty strings, got {s!r}"
            )
        if s in signal_id_set:
            raise CoreTaxonomyValidationError(
                f"core taxonomy 'signal_ids' contains duplicate: '{s}'"
            )
        signal_id_set.add(s)

    dimensions = taxonomy.get("dimensions")
    if dimensions is not None:
        if not isinstance(dimensions, dict):
            raise CoreTaxonomyValidationError("core taxonomy 'dimensions' must be a dict")
        for dim_key, dim_ids in dimensions.items():
            if not isinstance(dim_ids, list):
                raise CoreTaxonomyValidationError(
                    f"core taxonomy dimensions.{dim_key} must be a list"
                )
            for sid in dim_ids:
                if sid not in signal_id_set:
                    raise CoreTaxonomyValidationError(
                        f"core taxonomy dimensions.{dim_key} references '{sid}' not in signal_ids"
                    )

    _validate_signals(taxonomy, signal_id_set)
