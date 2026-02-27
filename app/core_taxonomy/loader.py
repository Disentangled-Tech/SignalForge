"""Core signal taxonomy loader (Issue #285, Milestone 1).

Provides canonical signal_ids and dimension structure that is pack-independent.
Labels and explainability_templates remain pack-specific.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_TAXONOMY_PATH = Path(__file__).parent / "taxonomy.yaml"


@lru_cache(maxsize=1)
def load_core_taxonomy() -> dict[str, Any]:
    """Load and return the core taxonomy YAML content.

    Validates the loaded content on every call. Use :func:`get_core_signal_ids`
    for a cached accessor when only the signal_id set is needed.

    Returns:
        Dict with at least 'signal_ids' (list[str]) and optionally 'dimensions'.

    Raises:
        FileNotFoundError: If taxonomy.yaml is missing.
        CoreTaxonomyValidationError: If taxonomy is structurally invalid.
    """
    from app.core_taxonomy.validator import validate_core_taxonomy

    try:
        with _TAXONOMY_PATH.open() as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Core taxonomy YAML is malformed: {exc}") from exc
    validate_core_taxonomy(data)
    return data


@lru_cache(maxsize=1)
def get_core_signal_ids() -> frozenset[str]:
    """Return the canonical set of core signal_ids (cached after first call).

    Returns:
        frozenset of signal_id strings.
    """
    taxonomy = load_core_taxonomy()
    return frozenset(taxonomy.get("signal_ids") or [])


@lru_cache(maxsize=1)
def get_core_taxonomy_version() -> str:
    """Return the core taxonomy version for evidence store recording.

    Reads optional top-level 'version' from taxonomy.yaml; if present and
    non-empty, returns it. Otherwise returns a stable SHA-256 hex digest
    of the file content (64 chars). Used by the Evidence Store (Issue #276).

    Returns:
        Non-empty version string (human-readable or content hash).
    """
    data = load_core_taxonomy()
    version = data.get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return hashlib.sha256(_TAXONOMY_PATH.read_bytes()).hexdigest()


def is_valid_signal_id(signal_id: str) -> bool:
    """Return True if signal_id is in the core taxonomy.

    Args:
        signal_id: The signal identifier to check.

    Returns:
        True if signal_id is a known core signal; False otherwise.
    """
    return signal_id in get_core_signal_ids()
