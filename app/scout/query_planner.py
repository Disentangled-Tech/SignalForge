"""Scout Query Planner — generates search queries from ICP and core rubric (read-only).

Per plan Step 3: no DB, no HTTP. Optional pack_id for emphasis hints only.
"""

from __future__ import annotations

from app.core_taxonomy.loader import load_core_taxonomy


def plan(
    icp_definition: str,
    core_rubric: dict | None = None,
    pack_id: str | None = None,
) -> list[str]:
    """Produce a list of diversified search query strings from ICP and core rubric.

    Args:
        icp_definition: Ideal Customer Profile description (free text).
        core_rubric: Core taxonomy dict (signal_ids, dimensions). If None, loaded via load_core_taxonomy().
        pack_id: Optional pack id for emphasis hints (query phrasing only). Currently unused.

    Returns:
        Non-empty list of query strings. At least one query derived from ICP; may add
        rubric-based phrasing for diversity.
    """
    if core_rubric is None:
        core_rubric = load_core_taxonomy()
    queries: list[str] = []
    icp = (icp_definition or "").strip()
    if icp:
        queries.append(icp)
    signal_ids = core_rubric.get("signal_ids") or []
    dimensions = core_rubric.get("dimensions") or {}
    if signal_ids:
        sample = list(signal_ids)[:5]
        phrase = " ".join(sample).replace("_", " ")
        if phrase and phrase not in queries:
            queries.append(phrase)
    if dimensions and not queries:
        fallback = "startup signals hiring growth"
        queries.append(fallback)
    if not queries:
        queries = ["startup company signals"]
    return queries
