"""Core signal taxonomy package (Issue #285, Milestone 1).

Exposes canonical signal_ids that are pack-independent. Labels and
explainability_templates remain pack-specific.
"""

from __future__ import annotations

from app.core_taxonomy.loader import get_core_signal_ids, is_valid_signal_id, load_core_taxonomy

__all__ = ["get_core_signal_ids", "is_valid_signal_id", "load_core_taxonomy"]
