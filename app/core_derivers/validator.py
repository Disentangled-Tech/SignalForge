"""Core Derivers validator (Issue #285, Milestone 2).

Validates core derivers YAML schema: passthrough entries reference only
signal_ids in core taxonomy; pattern regex is safe (ADR-008).
"""

from __future__ import annotations

from typing import Any


def validate_core_derivers(derivers: dict[str, Any], core_signal_ids: frozenset[str]) -> None:
    """Validate core derivers schema and cross-references.

    Args:
        derivers: Loaded derivers dict (from derivers.yaml).
        core_signal_ids: Frozenset of valid signal_ids from core taxonomy.

    Raises:
        ValueError: When derivers structure is invalid or references unknown
            signal_ids; or when a pattern fails regex safety checks.
    """
    if not isinstance(derivers, dict):
        raise ValueError("Core derivers must be a dict")

    inner = derivers.get("derivers") or derivers
    if not isinstance(inner, dict):
        raise ValueError("Core derivers must have a 'derivers' key containing a dict")

    passthrough = inner.get("passthrough") or []
    if not isinstance(passthrough, list):
        raise ValueError("Core derivers 'passthrough' must be a list")
    for i, item in enumerate(passthrough):
        if not isinstance(item, dict):
            raise ValueError(f"Passthrough entry {i} must be a dict")
        etype = item.get("event_type")
        sid = item.get("signal_id")
        if not etype or not isinstance(etype, str):
            raise ValueError(f"Passthrough entry {i} must have a non-empty 'event_type'")
        if not sid or not isinstance(sid, str):
            raise ValueError(f"Passthrough entry {i} must have a non-empty 'signal_id'")
        if sid not in core_signal_ids:
            raise ValueError(
                f"Passthrough entry {i} references unknown signal_id '{sid}'"
            )

    pattern_list = inner.get("pattern") or []
    if not isinstance(pattern_list, list):
        raise ValueError("Core derivers 'pattern' must be a list")
    if pattern_list:
        from app.packs.regex_validator import validate_deriver_regex_safety

        validate_deriver_regex_safety(derivers)
        for i, item in enumerate(pattern_list):
            if not isinstance(item, dict):
                raise ValueError(f"Pattern entry {i} must be a dict")
            sid = item.get("signal_id")
            if not sid or not isinstance(sid, str):
                raise ValueError(f"Pattern entry {i} must have a non-empty 'signal_id'")
            if sid not in core_signal_ids:
                raise ValueError(
                    f"Pattern entry {i} references unknown signal_id '{sid}'"
                )
