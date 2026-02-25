"""SignalScorer: band resolution from composite score (Issue #242, Phase 2).

Resolves recommendation band (IGNORE / WATCH / HIGH_PRIORITY) from composite
score and pack recommendation_bands config. Used by snapshot_writer to persist
band in ReadinessSnapshot.explain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.packs.loader import Pack


def resolve_band(composite: int, pack: Pack | None) -> str | None:
    """Resolve recommendation band from composite score and pack config.

    When pack has recommendation_bands (ignore_max, watch_max, high_priority_min),
    returns IGNORE | WATCH | HIGH_PRIORITY. When pack has no bands, returns None.

    Bands are inclusive: composite <= ignore_max -> IGNORE;
    ignore_max < composite <= watch_max -> WATCH;
    composite >= high_priority_min -> HIGH_PRIORITY.
    """
    if pack is None:
        return None
    sc = pack.scoring if isinstance(pack.scoring, dict) else {}
    bands = sc.get("recommendation_bands")
    if not bands or not isinstance(bands, dict):
        return None
    ignore_max = bands.get("ignore_max")
    watch_max = bands.get("watch_max")
    high_priority_min = bands.get("high_priority_min")
    if ignore_max is None or watch_max is None or high_priority_min is None:
        return None
    try:
        ig = int(ignore_max)
        wm = int(watch_max)
        hp = int(high_priority_min)
    except (TypeError, ValueError):
        return None
    if not (ig < wm < hp):
        return None
    if composite <= ig:
        return "IGNORE"
    if composite <= wm:
        return "WATCH"
    return "HIGH_PRIORITY"
