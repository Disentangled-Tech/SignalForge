"""Human-readable labels for event types (v2-spec §16, Issue #93).

Phase 2 (CTO Pack Extraction): Labels loaded from pack taxonomy.labels.
No hardcoded fallback; when pack is None, uses formatted event_type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.packs.loader import Pack


def event_type_to_label(event_type: str, pack: Pack | None = None) -> str:
    """Return human-readable label for event_type.

    Phase 2: When pack is provided, uses pack.taxonomy.labels. When pack is
    None or label not found, falls back to formatted type (e.g. "cto_role_posted"
    -> "Cto Role Posted").
    """
    if not event_type:
        return "Signal"
    if pack is not None and isinstance(pack.taxonomy, dict):
        labels = pack.taxonomy.get("labels") or {}
        if isinstance(labels, dict) and event_type in labels:
            return str(labels[event_type])
    return event_type.replace("_", " ").title()
