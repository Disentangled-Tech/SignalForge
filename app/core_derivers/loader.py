"""Core derivers loader (Issue #285, Milestone 2).

Provides pack-independent canonical event_type -> signal_id passthrough mappings
and compiled pattern derivers for the derive stage. Use get_core_passthrough_map()
and get_core_pattern_derivers() for cached access.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from app.core_derivers.validator import validate_core_derivers
from app.packs.schemas import ALLOWED_PATTERN_SOURCE_FIELDS

logger = logging.getLogger(__name__)

_DERIVERS_PATH = Path(__file__).parent / "derivers.yaml"

# Default fields to search when source_fields not specified (mirrors deriver_engine)
_DEFAULT_PATTERN_SOURCE_FIELDS = ("title", "summary")


@lru_cache(maxsize=1)
def load_core_derivers() -> dict[str, Any]:
    """Load and validate core derivers YAML. Result is cached after first call.

    Returns:
        Dict with 'derivers' key containing 'passthrough' and optional 'pattern'.

    Raises:
        FileNotFoundError: If derivers.yaml is missing.
        ValueError: If derivers.yaml is malformed or fails schema validation.
    """
    try:
        with _DERIVERS_PATH.open() as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Core derivers YAML is malformed: {exc}") from exc
    validate_core_derivers(data)
    return data


@lru_cache(maxsize=1)
def get_core_passthrough_map() -> Mapping[str, str]:
    """Return a read-only map from event_type -> signal_id for all core passthrough derivers.

    The returned mapping is immutable (MappingProxyType) to prevent accidental
    mutation of the cached shared reference. It supports all read operations
    (get, in, items, etc.) identically to a plain dict.

    Returns:
        Read-only mapping of event_type str -> signal_id str.
    """
    derivers = load_core_derivers()
    inner = derivers.get("derivers") or {}
    passthrough = inner.get("passthrough") or []
    result: dict[str, str] = {
        entry["event_type"]: entry["signal_id"]
        for entry in passthrough
        if isinstance(entry, dict) and "event_type" in entry and "signal_id" in entry
    }
    return MappingProxyType(result)


@lru_cache(maxsize=1)
def get_core_pattern_derivers() -> tuple[dict[str, Any], ...]:
    """Return compiled core pattern derivers ready for _evaluate_event_derivers.

    Returns tuple (for hashability with lru_cache) of dicts:
        {signal_id, compiled, source_fields, min_confidence}
    """
    derivers = load_core_derivers()
    inner = derivers.get("derivers") or derivers
    pattern_list = inner.get("pattern") if isinstance(inner, dict) else []
    if not isinstance(pattern_list, list):
        return ()
    result: list[dict[str, Any]] = []
    for item in pattern_list:
        if not isinstance(item, dict):
            continue
        sid = item.get("signal_id")
        pat_str = item.get("pattern") or item.get("regex")
        if not sid or not pat_str:
            continue
        try:
            compiled = re.compile(pat_str)
        except re.error:
            logger.warning(
                "Invalid core pattern deriver regex for signal_id=%s, skipping", sid
            )
            continue
        source_fields = item.get("source_fields")
        if source_fields is None:
            source_fields = list(_DEFAULT_PATTERN_SOURCE_FIELDS)
        elif not isinstance(source_fields, list):
            source_fields = list(_DEFAULT_PATTERN_SOURCE_FIELDS)
        else:
            source_fields = [f for f in source_fields if f in ALLOWED_PATTERN_SOURCE_FIELDS]
            if not source_fields:
                source_fields = list(_DEFAULT_PATTERN_SOURCE_FIELDS)
        min_confidence = item.get("min_confidence")
        if min_confidence is not None:
            min_confidence = float(min_confidence)
        result.append(
            {
                "signal_id": str(sid),
                "compiled": compiled,
                "source_fields": source_fields,
                "min_confidence": min_confidence,
            }
        )
    return tuple(result)
