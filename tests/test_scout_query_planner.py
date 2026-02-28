"""Tests for scout Query Planner — read-only core taxonomy + optional pack emphasis.

Given fixed ICP + rubric, output is non-empty and contains expected query shapes;
optional pack_id changes emphasis, not structure. No DB, no HTTP.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.scout.query_planner import QueryPlanner, plan_queries


def _minimal_core_rubric() -> dict:
    """Minimal core taxonomy shape: signal_ids + dimensions."""
    return {
        "signal_ids": ["funding_raised", "cto_role_posted", "headcount_growth"],
        "dimensions": {
            "M": ["funding_raised", "headcount_growth"],
            "G": ["cto_role_posted"],
        },
    }


# ── plan returns non-empty, expected shape ───────────────────────────────────


def test_plan_returns_non_empty_given_icp_and_rubric() -> None:
    """Given fixed ICP and core rubric, plan() returns a non-empty list of query strings."""
    planner = QueryPlanner()
    queries = planner.plan(
        icp="Seed-stage B2B SaaS in fintech",
        core_rubric=_minimal_core_rubric(),
    )
    assert isinstance(queries, list)
    assert len(queries) > 0
    for q in queries:
        assert isinstance(q, str)
        assert len(q.strip()) > 0


def test_plan_uses_core_taxonomy_when_rubric_none() -> None:
    """When core_rubric is None, planner loads from load_core_taxonomy() and returns non-empty."""
    planner = QueryPlanner()
    queries = planner.plan(icp="Startups hiring technical leadership", core_rubric=None)
    assert isinstance(queries, list)
    assert len(queries) > 0
    for q in queries:
        assert isinstance(q, str)
        assert q.strip()


def test_plan_query_shapes_contain_icp_and_signal_related_phrases() -> None:
    """Output queries incorporate ICP text and rubric-derived phrases (diversified)."""
    planner = QueryPlanner()
    icp = "B2B SaaS fintech"
    rubric = _minimal_core_rubric()
    queries = planner.plan(icp=icp, core_rubric=rubric)
    assert len(queries) >= 1
    # At least one query should contain ICP-related wording
    icp_lower = icp.lower()
    assert any(icp_lower in q.lower() for q in queries)
    # At least one query should reflect rubric (e.g. funding, CTO, headcount)
    rubric_phrases = ["funding", "cto", "headcount", "role", "growth"]
    assert any(any(p in q.lower() for p in rubric_phrases) for q in queries), (
        f"Expected some rubric-derived phrasing in {queries}"
    )


def test_plan_with_pack_id_no_emphasis_unchanged_structure() -> None:
    """When pack_id is provided but pack has no scout_emphasis, result is still list[str]."""
    planner = QueryPlanner()
    # Use a real pack that has no scout_emphasis key (e.g. example_v2)
    queries = planner.plan(
        icp="Any startup",
        core_rubric=_minimal_core_rubric(),
        pack_id="example_v2",
    )
    assert isinstance(queries, list)
    assert len(queries) > 0
    for q in queries:
        assert isinstance(q, str)


def test_optional_pack_id_adds_emphasis_not_structure(tmp_path: Path) -> None:
    """When pack has scout_emphasis, queries include those keywords; structure remains list[str]."""
    (tmp_path / "pack.json").write_text(
        json.dumps(
            {
                "id": "test_scout_pack",
                "version": "1",
                "name": "Test",
                "scout_emphasis": ["fractional CTO", "technical leadership"],
            }
        ),
        encoding="utf-8",
    )
    planner = QueryPlanner()
    with patch("app.scout.query_planner.get_pack_dir", return_value=tmp_path):
        queries = planner.plan(
            icp="B2B SaaS",
            core_rubric=_minimal_core_rubric(),
            pack_id="test_scout_pack",
        )
    assert isinstance(queries, list)
    assert len(queries) > 0
    combined = " ".join(queries).lower()
    assert "fractional" in combined or "cto" in combined
    assert "technical" in combined or "leadership" in combined


def test_plan_queries_convenience_function() -> None:
    """plan_queries() is a convenience that returns same shape as QueryPlanner().plan()."""
    queries = plan_queries(
        icp="Fintech startup",
        core_rubric=_minimal_core_rubric(),
    )
    assert isinstance(queries, list)
    assert len(queries) > 0
    for q in queries:
        assert isinstance(q, str)


def test_plan_no_duplicate_queries() -> None:
    """Planner returns deduplicated queries (no exact duplicate strings)."""
    planner = QueryPlanner()
    queries = planner.plan(
        icp="SaaS",
        core_rubric=_minimal_core_rubric(),
    )
    assert len(queries) == len(set(queries)), "Queries should be deduplicated"
