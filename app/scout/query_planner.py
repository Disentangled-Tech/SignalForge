"""Query Planner for LLM Discovery Scout — read-only, produces search query strings.

Uses core taxonomy (and optional pack_id for emphasis) for query phrasing only.
No DB writes, no HTTP. Per plan Step 3 / M2.
"""

from __future__ import annotations


def plan(
    icp_definition: str,
    core_rubric: dict | None = None,
    pack_id: str | None = None,
) -> list[str]:
    """Produce a list of diversified search query strings from ICP and core rubric.

    Args:
        icp_definition: Ideal Customer Profile description (e.g. "Seed-stage B2B SaaS").
        core_rubric: Optional dict from load_core_taxonomy() (signal_ids, dimensions).
        pack_id: Optional pack identifier for emphasis hints (e.g. fractional CTO keywords).

    Returns:
        Non-empty list of query strings. At least one query derived from ICP.
    """
    queries: list[str] = []
    icp = (icp_definition or "").strip()
    if not icp:
        return ["startup hiring growth"]

    # Base queries from ICP
    queries.append(f"{icp} startup")
    queries.append(f"{icp} company hiring")
    queries.append(f"{icp} funding news")

    # Optional: add emphasis from core rubric (readiness-related phrasing)
    if core_rubric:
        signal_ids = core_rubric.get("signal_ids") or []
        if isinstance(signal_ids, list) and len(signal_ids) > 0:
            # Use a few representative signals for query diversity (no pack-specific logic)
            for sid in signal_ids[:5]:
                if isinstance(sid, str) and sid in (
                    "funding_raised",
                    "job_posted_engineering",
                    "cto_role_posted",
                ):
                    queries.append(f"{icp} {sid.replace('_', ' ')}")
                    break

    # Optional pack emphasis: add one query hint (query text only, no derivation)
    if pack_id and isinstance(pack_id, str) and pack_id.strip():
        pid = pack_id.strip().lower()
        if "cto" in pid:
            queries.append(f"{icp} CTO hiring fractional")
        elif "cfo" in pid:
            queries.append(f"{icp} CFO finance")
        elif "coo" in pid or "cmo" in pid:
            queries.append(f"{icp} operations growth")

    return list(dict.fromkeys(queries)) if queries else [f"{icp} startup"]
