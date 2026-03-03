"""Query family definitions and config loader for Discovery Scout (Issue #282).

Pack-agnostic: family ids and template slots. Query packs are config-based:
edit query_families.yaml to add or change families/templates; no code change required.
If query_families.yaml is missing, in-code default (single 'rubric' family) is used
so planner falls back to rubric-only query generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Family ids used in config and plan_with_families() output.
# Pack only provides optional scout_emphasis; families are core-owned.
HIRING = "hiring"
LAUNCH = "launch"
GEOGRAPHY = "geography"
ROLE_EMPHASIS = "role_emphasis"
NICHE = "niche"

# Fallback family when YAML is missing: all rubric-derived queries get this tag.
DEFAULT_FAMILY_ID = "rubric"

_QUERY_FAMILIES_PATH = Path(__file__).parent / "query_families.yaml"


def _default_families_config() -> list[dict[str, Any]]:
    """In-code default: single rubric family (empty templates = use rubric phrases)."""
    return [
        {
            "id": DEFAULT_FAMILY_ID,
            "label": "Rubric",
            "templates": [],
        }
    ]


def _validate_family_entry(entry: Any, index: int) -> dict[str, Any] | None:
    """Return validated family dict or None if invalid."""
    if not isinstance(entry, dict):
        return None
    fid = entry.get("id")
    if not isinstance(fid, str) or not fid.strip():
        return None
    label = entry.get("label")
    if not isinstance(label, str):
        label = fid
    templates = entry.get("templates")
    if not isinstance(templates, list):
        templates = []
    templates = [str(t).strip() for t in templates if t is not None and str(t).strip()]
    return {"id": fid.strip(), "label": label.strip() or fid.strip(), "templates": templates}


def load_query_families_config(path: Path | None = None) -> list[dict[str, Any]]:
    """Load query family config from YAML or return in-code default.

    Args:
        path: Override path to query_families.yaml (for tests). If None, uses
            app/scout/query_families.yaml.

    Returns:
        List of dicts with keys: id, label, templates (list of str).
        When file is missing or invalid, returns single family with id 'rubric'.
    """
    use_path = path if path is not None else _QUERY_FAMILIES_PATH
    if not use_path.is_file():
        return _default_families_config()
    try:
        with use_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return _default_families_config()
    if not isinstance(raw, list) or len(raw) == 0:
        return _default_families_config()
    result: list[dict[str, Any]] = []
    for i, entry in enumerate(raw):
        validated = _validate_family_entry(entry, i)
        if validated is not None:
            result.append(validated)
    if not result:
        return _default_families_config()
    return result
