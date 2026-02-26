"""Core taxonomy schema validation (Issue #285, Milestone 1).

Validates that core taxonomy.yaml has the required structure:
- signal_ids: non-empty list of unique strings
- dimensions (optional): dict of dimension_key -> list of signal_ids (must reference signal_ids)
"""

from __future__ import annotations

from typing import Any


class CoreTaxonomyValidationError(ValueError):
    """Raised when core taxonomy validation fails.

    Subclasses ValueError so callers can catch it via ``except ValueError``
    alongside ``FileNotFoundError`` without needing to import this class.
    """


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
