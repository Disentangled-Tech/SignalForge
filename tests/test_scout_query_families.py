"""Tests for scout query families and rotation (M1 — Discovery Query Planner #282).

Covers: family constants, plan_with_families() return shape, rotation across families,
and fallback when query_families.yaml is missing. plan() and plan_queries() remain
unchanged (tested in test_scout_query_planner.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.scout.query_families import (
    DEFAULT_FAMILY_ID,
    load_query_families_config,
)
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


# ── Loader: missing YAML falls back to in-code default ───────────────────────


def test_load_query_families_config_missing_yaml_returns_default() -> None:
    """When query_families.yaml is missing, loader returns single default family (rubric)."""
    with patch(
        "app.scout.query_families._QUERY_FAMILIES_PATH", Path("/nonexistent/query_families.yaml")
    ):
        config = load_query_families_config()
    assert isinstance(config, list)
    assert len(config) >= 1
    default = next((f for f in config if f.get("id") == DEFAULT_FAMILY_ID), None)
    assert default is not None
    assert default.get("label")
    assert "templates" in default


def test_load_query_families_config_with_yaml_returns_families(tmp_path: Path) -> None:
    """When YAML exists with multiple families, loader returns them."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text(
        """
- id: hiring
  label: Hiring
  templates:
    - "{icp} hiring"
    - "hiring {icp}"
- id: launch
  label: Launch
  templates:
    - "{icp} launch"
""",
        encoding="utf-8",
    )
    with patch("app.scout.query_families._QUERY_FAMILIES_PATH", yaml_path):
        config = load_query_families_config()
    assert len(config) == 2
    ids = [f["id"] for f in config]
    assert "hiring" in ids
    assert "launch" in ids
    hiring = next(f for f in config if f["id"] == "hiring")
    assert hiring["templates"] == ["{icp} hiring", "hiring {icp}"]


# ── plan_with_families return shape and allowed set ───────────────────────────


def test_plan_with_families_returns_same_length_queries_and_families() -> None:
    """plan_with_families() returns (queries, families) with same length."""
    planner = QueryPlanner(max_queries=20)
    queries, families = planner.plan_with_families(
        icp="B2B SaaS",
        core_rubric=_minimal_core_rubric(),
    )
    assert isinstance(queries, list)
    assert isinstance(families, list)
    assert len(queries) == len(families)
    assert len(queries) >= 1
    for q in queries:
        assert isinstance(q, str)
        assert q.strip()
    for f in families:
        assert isinstance(f, str)
        assert f


def test_plan_with_families_families_from_allowed_set() -> None:
    """All returned family ids are from the configured set (default: rubric when YAML missing)."""
    with patch(
        "app.scout.query_families._QUERY_FAMILIES_PATH", Path("/nonexistent/query_families.yaml")
    ):
        planner = QueryPlanner(max_queries=15)
        _, families = planner.plan_with_families(
            icp="Fintech startup",
            core_rubric=_minimal_core_rubric(),
        )
    allowed = {DEFAULT_FAMILY_ID}
    for fid in families:
        assert fid in allowed, f"Family id {fid!r} not in allowed set {allowed}"


def test_plan_with_families_with_yaml_returns_config_families(tmp_path: Path) -> None:
    """When YAML is present, returned family ids are from config or rubric (rubric added from core phrases)."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text(
        """
- id: hiring
  label: Hiring
  templates:
    - "{icp} hiring"
    - "hiring {icp}"
- id: launch
  label: Launch
  templates:
    - "{icp} launch"
""",
        encoding="utf-8",
    )
    with patch("app.scout.query_families._QUERY_FAMILIES_PATH", yaml_path):
        planner = QueryPlanner(max_queries=20)
        _, families = planner.plan_with_families(icp="SaaS", core_rubric=_minimal_core_rubric())
    # Config families + default rubric (rubric-derived queries still included)
    allowed = {"hiring", "launch", DEFAULT_FAMILY_ID}
    for fid in families:
        assert fid in allowed, f"Family id {fid!r} not in {allowed}"
    # At least one config family appears (templates were used)
    assert "hiring" in families or "launch" in families


# ── Rotation: multiple families appear in result ──────────────────────────────


def test_rotation_produces_at_least_two_families_when_multiple_exist(tmp_path: Path) -> None:
    """When config has multiple families, rotation produces at least two distinct families."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text(
        """
- id: hiring
  label: Hiring
  templates:
    - "{icp} hiring"
    - "hiring {icp}"
- id: launch
  label: Launch
  templates:
    - "{icp} launch"
    - "launch {icp}"
""",
        encoding="utf-8",
    )
    with patch("app.scout.query_families._QUERY_FAMILIES_PATH", yaml_path):
        planner = QueryPlanner(max_queries=20)
        _, families = planner.plan_with_families(icp="Startup", core_rubric=_minimal_core_rubric())
    distinct = set(families)
    assert len(distinct) >= 2, f"Expected at least 2 families in rotation, got {distinct}"


# ── Fallback: no crash when YAML missing ─────────────────────────────────────


def test_missing_query_families_yaml_falls_back_no_crash() -> None:
    """When query_families.yaml is missing, plan_with_families runs without error."""
    with patch(
        "app.scout.query_families._QUERY_FAMILIES_PATH", Path("/nonexistent/query_families.yaml")
    ):
        planner = QueryPlanner()
        queries, families = planner.plan_with_families(
            icp="Any ICP",
            core_rubric=_minimal_core_rubric(),
        )
    assert len(queries) >= 1
    assert len(families) == len(queries)
    assert all(f == DEFAULT_FAMILY_ID for f in families)


# ── Regression: plan() and plan_queries() unchanged ──────────────────────────


def test_plan_still_returns_list_str_after_families_added() -> None:
    """plan() still returns list[str] only (no signature/return change)."""
    planner = QueryPlanner()
    result = planner.plan(
        icp="B2B SaaS",
        core_rubric=_minimal_core_rubric(),
    )
    assert isinstance(result, list)
    assert all(isinstance(x, str) for x in result)


def test_plan_queries_still_returns_list_str_after_families_added() -> None:
    """plan_queries() still returns list[str] only (no signature change)."""
    result = plan_queries(
        icp="Fintech",
        core_rubric=_minimal_core_rubric(),
    )
    assert isinstance(result, list)
    assert all(isinstance(x, str) for x in result)


def test_plan_with_families_deduplicated() -> None:
    """plan_with_families() returns deduplicated query strings."""
    planner = QueryPlanner(max_queries=50)
    queries, _ = planner.plan_with_families(
        icp="SaaS",
        core_rubric=_minimal_core_rubric(),
    )
    assert len(queries) == len(set(queries)), "Queries should be deduplicated"


def test_plan_with_families_same_queries_as_plan_when_same_inputs() -> None:
    """plan() returns the same query list as plan_with_families()[0] for same inputs."""
    planner = QueryPlanner(max_queries=25)
    icp = "B2B fintech"
    rubric = _minimal_core_rubric()
    plan_queries_list = planner.plan(icp=icp, core_rubric=rubric)
    with_families_queries, _ = planner.plan_with_families(icp=icp, core_rubric=rubric)
    assert plan_queries_list == with_families_queries


# ── query_families loader: validation and error paths (coverage ≥85%) ─────────


def test_load_query_families_config_invalid_yaml_returns_default(tmp_path: Path) -> None:
    """When YAML is malformed, loader returns default config."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text("not: valid: yaml: [", encoding="utf-8")
    config = load_query_families_config(path=yaml_path)
    assert len(config) == 1
    assert config[0]["id"] == DEFAULT_FAMILY_ID


def test_load_query_families_config_empty_list_returns_default(tmp_path: Path) -> None:
    """When YAML parses to empty list, loader returns default."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text("[]", encoding="utf-8")
    config = load_query_families_config(path=yaml_path)
    assert len(config) == 1
    assert config[0]["id"] == DEFAULT_FAMILY_ID


def test_load_query_families_config_non_list_returns_default(tmp_path: Path) -> None:
    """When YAML parses to non-list, loader returns default."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text("id: hiring", encoding="utf-8")
    config = load_query_families_config(path=yaml_path)
    assert len(config) == 1
    assert config[0]["id"] == DEFAULT_FAMILY_ID


def test_load_query_families_config_all_invalid_entries_returns_default(tmp_path: Path) -> None:
    """When all entries are invalid (e.g. missing id), loader returns default."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text(
        """
- label: Only label
  templates: []
- id: ""
  label: Empty id
- id: 123
  label: 124
""",
        encoding="utf-8",
    )
    config = load_query_families_config(path=yaml_path)
    assert len(config) == 1
    assert config[0]["id"] == DEFAULT_FAMILY_ID


def test_load_query_families_config_non_dict_entry_skipped(tmp_path: Path) -> None:
    """When an entry is not a dict (e.g. string or number), it is skipped."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text(
        """
- "not a dict"
- 42
- id: hiring
  label: Hiring
  templates: []
""",
        encoding="utf-8",
    )
    config = load_query_families_config(path=yaml_path)
    assert len(config) == 1
    assert config[0]["id"] == "hiring"


def test_load_query_families_config_entry_with_non_str_label_uses_id_as_label(
    tmp_path: Path,
) -> None:
    """When label is not a string, validated entry uses id as label."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text(
        """
- id: hiring
  label: 42
  templates:
    - "{icp} hiring"
""",
        encoding="utf-8",
    )
    config = load_query_families_config(path=yaml_path)
    assert len(config) == 1
    assert config[0]["id"] == "hiring"
    assert config[0]["label"] == "hiring"


def test_load_query_families_config_entry_with_non_list_templates_treated_as_empty(
    tmp_path: Path,
) -> None:
    """When templates is not a list, it is treated as empty."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text(
        """
- id: hiring
  label: Hiring
  templates: "not a list"
""",
        encoding="utf-8",
    )
    config = load_query_families_config(path=yaml_path)
    assert len(config) == 1
    assert config[0]["templates"] == []


# ── M4: Config-based query packs — YAML used for template expansion when present ─


def test_config_based_query_pack_yaml_present_templates_expanded(tmp_path: Path) -> None:
    """When YAML is present, template expansion uses config: {icp} replaced, family from config."""
    yaml_path = tmp_path / "query_families.yaml"
    yaml_path.write_text(
        """
- id: hiring
  label: Hiring
  templates:
    - "{icp} hiring"
    - "hiring {icp}"
""",
        encoding="utf-8",
    )
    with patch("app.scout.query_families._QUERY_FAMILIES_PATH", yaml_path):
        planner = QueryPlanner(max_queries=10)
        queries, families = planner.plan_with_families(
            icp="SaaS",
            core_rubric=_minimal_core_rubric(),
        )
    assert "SaaS hiring" in queries
    assert "hiring SaaS" in queries
    assert "hiring" in families
    idx = queries.index("SaaS hiring")
    assert families[idx] == "hiring"


def test_config_based_query_pack_yaml_missing_no_config_families() -> None:
    """When YAML is missing, only rubric family appears (no config-derived families)."""
    with patch(
        "app.scout.query_families._QUERY_FAMILIES_PATH", Path("/nonexistent/query_families.yaml")
    ):
        planner = QueryPlanner(max_queries=20)
        _, families = planner.plan_with_families(
            icp="Any ICP",
            core_rubric=_minimal_core_rubric(),
        )
    assert all(f == DEFAULT_FAMILY_ID for f in families)
