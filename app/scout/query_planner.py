"""Query Planner for Discovery Scout — read-only core taxonomy + optional pack emphasis.

Produces a diversified list of search query strings from ICP, core readiness signal
rubric (dimensions/signal_ids for query phrasing only), and optional pack emphasis.
No DB, no HTTP. Used only in the Scout path.
"""

from __future__ import annotations

import json
from typing import Any

from app.core_taxonomy.loader import load_core_taxonomy
from app.packs.loader import get_pack_dir

# Known acronyms to keep uppercase in query phrases (read-only, query phrasing only).
_ACRONYMS = frozenset({"cto", "cfo", "coo", "cmo", "api", "ai", "saas", "b2b", "b2c", "ipo"})


def _signal_id_to_phrase(signal_id: str) -> str:
    """Convert signal_id (snake_case) to a readable search phrase."""
    if not signal_id or not isinstance(signal_id, str):
        return ""
    parts = signal_id.strip().lower().split("_")
    words = []
    for p in parts:
        if p in _ACRONYMS:
            words.append(p.upper())
        else:
            words.append(p.capitalize() if p else "")
    return " ".join(w for w in words if w)


def _get_pack_emphasis(pack_id: str) -> list[str]:
    """Return scout_emphasis keywords from pack manifest if present; else [].

    Reads packs/{pack_id}/pack.json for optional 'scout_emphasis' (list of strings).
    Does not load full pack or run validation. Returns [] on missing file or invalid data.
    """
    if not pack_id or not isinstance(pack_id, str):
        return []
    try:
        pack_dir = get_pack_dir(pack_id)
        manifest_path = pack_dir / "pack.json"
        if not manifest_path.is_file():
            return []
        with manifest_path.open(encoding="utf-8") as f:
            manifest = json.load(f)
        emphasis = manifest.get("scout_emphasis")
        if not isinstance(emphasis, list):
            return []
        return [str(x).strip() for x in emphasis if x and isinstance(x, str)]
    except (OSError, ValueError, TypeError):
        return []


class QueryPlanner:
    """Plans diversified search queries from ICP, core rubric, and optional pack emphasis.

    Read-only: uses load_core_taxonomy() and optional pack manifest scout_emphasis.
    No DB, no HTTP.
    """

    def __init__(self, max_queries: int = 30) -> None:
        """Initialize planner with optional cap on number of queries (diversified set)."""
        self._max_queries = max(1, min(100, max_queries))

    def plan(
        self,
        icp: str,
        core_rubric: dict[str, Any] | None = None,
        pack_id: str | None = None,
    ) -> list[str]:
        """Produce a diversified list of search query strings.

        Args:
            icp: Ideal Customer Profile definition (free text).
            core_rubric: Core taxonomy dict (signal_ids, dimensions). If None, loads
                from load_core_taxonomy().
            pack_id: Optional pack id for emphasis hints (scout_emphasis in pack.json).

        Returns:
            Non-empty list of deduplicated query strings (no DB, no HTTP).
        """
        icp = (icp or "").strip()
        if not icp:
            icp = "startup"

        if core_rubric is None:
            core_rubric = load_core_taxonomy()

        seen: set[str] = set()
        queries: list[str] = []

        # Phrases from core rubric: use signal_ids for query phrasing (diversified).
        signal_ids = core_rubric.get("signal_ids") or []
        dimensions = core_rubric.get("dimensions") or {}
        # Collect phrases: one per dimension (first signal in each) + a subset of all
        phrases_from_rubric: list[str] = []
        for dim_ids in dimensions.values():
            if isinstance(dim_ids, list):
                for sid in dim_ids[:2]:  # up to 2 per dimension
                    if isinstance(sid, str):
                        phrase = _signal_id_to_phrase(sid)
                        if phrase and phrase not in phrases_from_rubric:
                            phrases_from_rubric.append(phrase)
        for sid in signal_ids:
            if isinstance(sid, str):
                phrase = _signal_id_to_phrase(sid)
                if phrase and phrase not in phrases_from_rubric:
                    phrases_from_rubric.append(phrase)
            if len(phrases_from_rubric) >= 15:
                break

        for phrase in phrases_from_rubric:
            for template in (f"{icp} {phrase}", f"{phrase} {icp}"):
                t = template.strip()
                if t and t not in seen:
                    seen.add(t)
                    queries.append(t)
            if len(queries) >= self._max_queries:
                break

        # Pack emphasis: add ICP + keyword (structure unchanged, emphasis only).
        if pack_id:
            for kw in _get_pack_emphasis(pack_id):
                if not kw:
                    continue
                for template in (f"{icp} {kw}", f"{kw} {icp}"):
                    t = template.strip()
                    if t and t not in seen:
                        seen.add(t)
                        queries.append(t)
                if len(queries) >= self._max_queries:
                    break

        # Ensure at least one query
        if not queries:
            queries = [icp]

        return queries[: self._max_queries]


def plan_queries(
    icp: str,
    core_rubric: dict[str, Any] | None = None,
    pack_id: str | None = None,
    max_queries: int = 30,
) -> list[str]:
    """Convenience: plan diversified search queries (QueryPlanner().plan())."""
    return QueryPlanner(max_queries=max_queries).plan(
        icp=icp,
        core_rubric=core_rubric,
        pack_id=pack_id,
    )
