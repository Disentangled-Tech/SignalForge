"""Core Signal Taxonomy loader (Issue #285, Milestone 1).

Provides a single source of truth for canonical signal identifiers that
is independent of any specific pack configuration.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core_taxonomy.validator import validate_core_taxonomy

_TAXONOMY_PATH = Path(__file__).parent / "taxonomy.yaml"


@lru_cache(maxsize=1)
def load_core_taxonomy() -> dict[str, Any]:
    """Load and validate core taxonomy YAML. Result is cached after first call.

    Returns:
        Dict with 'signal_ids' and optional 'dimensions'.

    Raises:
        FileNotFoundError: When taxonomy.yaml is missing.
        ValueError: When taxonomy fails schema validation.
    """
    with _TAXONOMY_PATH.open() as f:
        taxonomy: dict[str, Any] = yaml.safe_load(f) or {}
    validate_core_taxonomy(taxonomy)
    return taxonomy


@lru_cache(maxsize=1)
def get_core_signal_ids() -> frozenset[str]:
    """Return frozenset of canonical signal IDs from core taxonomy."""
    taxonomy = load_core_taxonomy()
    signal_ids = taxonomy.get("signal_ids") or []
    return frozenset(str(s) for s in signal_ids)


def is_valid_signal_id(signal_id: str) -> bool:
    """Return True if signal_id is in the core taxonomy."""
    return signal_id in get_core_signal_ids()
