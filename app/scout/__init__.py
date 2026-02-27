"""Scout (LLM Discovery) — Evidence-Only mode: query planning, source filter, evidence bundles.

No writes to companies, signal_events, or signal_instances.
"""

from app.scout.sources import filter_allowed_sources, is_source_allowed

__all__ = ["filter_allowed_sources", "is_source_allowed"]
