"""Core derivers package (Issue #285, Milestone 2).

Provides pack-independent canonical event_type -> signal_id mappings and
compiled pattern derivers for the derive stage.
"""
from __future__ import annotations

from app.core_derivers.loader import (
    get_core_passthrough_map,
    get_core_pattern_derivers,
    load_core_derivers,
)

__all__ = ["get_core_passthrough_map", "get_core_pattern_derivers", "load_core_derivers"]
