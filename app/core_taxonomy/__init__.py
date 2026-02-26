"""Core Signal Taxonomy (Issue #285, Milestone 1).

Provides pack-independent canonical signal identifiers for the derive stage.
"""

from app.core_taxonomy.loader import get_core_signal_ids, is_valid_signal_id, load_core_taxonomy

__all__ = ["get_core_signal_ids", "is_valid_signal_id", "load_core_taxonomy"]
