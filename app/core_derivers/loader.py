"""Core Derivers loader (Issue #285, Milestone 2).

Provides pack-independent canonical event_type -> signal_id passthrough mappings
and compiled pattern derivers for the derive stage.
"""Core derivers loader (Issue #285, Milestone 2).

Provides canonical passthrough and pattern derivers that are pack-independent.
Use get_core_passthrough_map() and get_core_pattern_derivers() for cached access.
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
from app.core_taxonomy.loader import get_core_signal_ids
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
        FileNotFoundError: When derivers.yaml is missing.
        ValueError: When derivers fail schema validation.
    """
    with _DERIVERS_PATH.open() as f:
        derivers: dict[str, Any] = yaml.safe_load(f) or {}
    validate_core_derivers(derivers, get_core_signal_ids())
    return derivers


@lru_cache(maxsize=1)
def get_core_passthrough_map() -> dict[str, str]:
    """Return canonical event_type -> signal_id passthrough map from core derivers."""
    derivers = load_core_derivers()
    inner = derivers.get("derivers") or derivers
    passthrough = inner.get("passthrough") if isinstance(inner, dict) else []
    if not isinstance(passthrough, list):
        return {}
    result: dict[str, str] = {}
    for item in passthrough:
        if isinstance(item, dict):
            etype = item.get("event_type")
            sid = item.get("signal_id")
            if etype and sid:
                result[str(etype)] = str(sid)
    return result
from app.packs.schemas import ALLOWED_PATTERN_SOURCE_FIELDS

_DERIVERS_PATH = Path(__file__).parent / "derivers.yaml"

# Default source fields when a pattern entry omits source_fields (mirrors deriver_engine)
_DEFAULT_PATTERN_SOURCE_FIELDS = ("title", "summary")

logger = logging.getLogger(__name__)


def load_core_derivers() -> dict[str, Any]:
    """Load and return the core derivers YAML content.

    Validates the loaded content on every call. Use :func:`get_core_passthrough_map`
    or :func:`get_core_pattern_derivers` for cached access.

    Returns:
        Dict with 'derivers' key containing 'passthrough' and optionally 'pattern' lists.
        Do not mutate the returned dict; its internal lists are shared by the cached
        accessors and mutation will silently corrupt cached state.

    Raises:
        FileNotFoundError: If derivers.yaml is missing.
        ValueError: If derivers.yaml is malformed YAML or fails schema/cross-reference
            validation (CoreDeriversValidationError is a ValueError subclass).
    """
    from app.core_derivers.validator import validate_core_derivers

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
    """Return compiled core pattern derivers ready for the deriver engine (cached).

    Each item is a dict with keys:
        - ``signal_id``: str
        - ``compiled``: compiled re.Pattern (field name matches deriver_engine convention)
        - ``source_fields``: list[str], filtered to ALLOWED_PATTERN_SOURCE_FIELDS
        - ``min_confidence``: float | None

    Returns a tuple (immutable container) for safe lru_cache usage. Do not mutate
    the inner dicts; they are shared cached references.

    Returns:
        Tuple of pattern deriver dicts ready for _evaluate_event_derivers.
    """
    derivers = load_core_derivers()
    inner = derivers.get("derivers") or {}
    pattern_list = inner.get("pattern") or []
    compiled: list[dict[str, Any]] = []
    for entry in pattern_list:
        if not isinstance(entry, dict):
            continue
        pat_str = entry.get("pattern") or entry.get("regex")
        if not pat_str:
            continue
        sid = entry.get("signal_id")
        if not sid:
            continue
        try:
            pattern_compiled = re.compile(str(pat_str))
        except re.error:
            logger.warning("Core derivers: invalid regex for signal_id=%s, skipping", sid)
            continue
        source_fields = entry.get("source_fields")
        if source_fields is None:
            effective_source_fields: list[str] = list(_DEFAULT_PATTERN_SOURCE_FIELDS)
        elif not isinstance(source_fields, list):
            effective_source_fields = list(_DEFAULT_PATTERN_SOURCE_FIELDS)
        else:
            effective_source_fields = [
                f for f in source_fields if f in ALLOWED_PATTERN_SOURCE_FIELDS
            ]
            if not effective_source_fields:
                effective_source_fields = list(_DEFAULT_PATTERN_SOURCE_FIELDS)
        min_confidence = entry.get("min_confidence")
        if min_confidence is not None:
            min_confidence = float(min_confidence)
        compiled.append(
            {
                "signal_id": str(sid),
                "compiled": pattern_compiled,
                "source_fields": effective_source_fields,
                "min_confidence": min_confidence,
            }
        )
    return tuple(compiled)
