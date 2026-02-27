"""Tests for scout query planner — read-only, output is list of query strings."""

from __future__ import annotations

from app.scout.query_planner import plan


def test_plan_returns_non_empty_list() -> None:
    """Given fixed ICP, output is non-empty."""
    queries = plan("Seed-stage B2B SaaS in fintech", core_rubric=None, pack_id=None)
    assert isinstance(queries, list)
    assert len(queries) >= 1
    assert all(isinstance(q, str) and len(q) > 0 for q in queries)


def test_plan_contains_expected_shapes() -> None:
    """Output contains query shapes derived from ICP."""
    icp = "Seed-stage B2B SaaS"
    queries = plan(icp, core_rubric=None, pack_id=None)
    assert any(icp in q for q in queries)
    assert any("startup" in q.lower() for q in queries)


def test_plan_with_core_rubric_adds_diversity() -> None:
    """Optional core_rubric can add signal-based query phrasing."""
    rubric = {"signal_ids": ["funding_raised", "job_posted_engineering", "cto_role_posted"]}
    queries = plan("Fintech", core_rubric=rubric, pack_id=None)
    assert len(queries) >= 1
    # May include a signal-derived query
    assert any("fintech" in q.lower() for q in queries)


def test_plan_with_pack_id_adds_emphasis() -> None:
    """Optional pack_id changes emphasis (e.g. CTO keywords)."""
    queries_cto = plan("B2B", core_rubric=None, pack_id="fractional_cto_v1")
    queries_cfo = plan("B2B", core_rubric=None, pack_id="fractional_cfo_v1")
    assert len(queries_cto) >= 1
    assert len(queries_cfo) >= 1
    assert any("CTO" in q or "cto" in q for q in queries_cto)
    assert any("CFO" in q or "cfo" in q or "finance" in q.lower() for q in queries_cfo)


def test_plan_empty_icp_returns_fallback() -> None:
    """Empty ICP returns a single fallback query."""
    queries = plan("", core_rubric=None, pack_id=None)
    assert queries == ["startup hiring growth"]


def test_plan_strips_icp() -> None:
    """Whitespace-only or stripped ICP is handled."""
    queries = plan("  Seed stage  ", core_rubric=None, pack_id=None)
    assert len(queries) >= 1
    assert any("Seed stage" in q for q in queries)
