"""Core Taxonomy validator (Issue #285, Milestone 1).

Validates the core taxonomy YAML schema: non-empty signal_ids list and
dimension entries that reference only known signal_ids.
"""

from __future__ import annotations

from typing import Any


def validate_core_taxonomy(taxonomy: dict[str, Any]) -> None:
    """Validate core taxonomy schema.

    Args:
        taxonomy: Loaded taxonomy dict (from taxonomy.yaml).

    Raises:
        ValueError: When taxonomy is structurally invalid or contains
            cross-reference errors.
    """
    if not isinstance(taxonomy, dict):
        raise ValueError("Core taxonomy must be a dict")

    signal_ids = taxonomy.get("signal_ids")
    if not signal_ids or not isinstance(signal_ids, list):
        raise ValueError("Core taxonomy must have a non-empty 'signal_ids' list")
    if not all(isinstance(s, str) and s for s in signal_ids):
        raise ValueError("All signal_ids must be non-empty strings")

    signal_id_set: frozenset[str] = frozenset(signal_ids)

    dimensions = taxonomy.get("dimensions")
    if dimensions is None:
        return
    if not isinstance(dimensions, dict):
        raise ValueError("Core taxonomy 'dimensions' must be a dict")
    for dim_key, dim_signals in dimensions.items():
        if not isinstance(dim_signals, list):
            raise ValueError(f"Dimension '{dim_key}' must be a list")
        for sid in dim_signals:
            if sid not in signal_id_set:
                raise ValueError(
                    f"Dimension '{dim_key}' references unknown signal_id '{sid}'"
                )
