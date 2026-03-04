"""ORE playbook contract: typed shape for pack playbooks (Issue #176, M1).

Defines the canonical structure for ORE playbooks so all consumers (draft generator,
pipeline, critic) use the same shape. Used by pack schema validation and playbook loader.

Required for ORE draft generation (get_ore_playbook / generate_ore_draft):
  - pattern_frames: dict[str, str] — dimension key to framing text
  - value_assets: list — offer strings (or value_statements can double as this)
  - ctas: list — call-to-action strings

Optional (M1 schema; loader/pipeline use in later milestones):
  - opening_templates: list of strings — optional email opening templates
  - value_statements: list — optional; can align with value_assets or extend them
  - forbidden_phrases: list of strings — phrases the critic must flag
  - tone: str | dict — tone instruction or map (e.g. per recommendation_type)

Existing playbooks (e.g. fractional_cto_v1) may only define pattern_frames, value_assets,
and ctas; validation allows optional keys to be absent.
"""

from __future__ import annotations

from typing import Any, TypedDict


class OREPlaybook(TypedDict, total=False):
    """Typed shape for ORE playbook YAML (ore_outreach etc.).

    Required for ORE: pattern_frames, value_assets, ctas.
    Optional: opening_templates, value_statements, forbidden_phrases, tone.
    Pack schema may also include sensitivity_levels, recommendation_types (ESL refs).
    """

    pattern_frames: dict[str, str]
    value_assets: list[Any]
    ctas: list[Any]
    opening_templates: list[str]
    value_statements: list[Any]
    forbidden_phrases: list[str]
    tone: str | dict[str, Any]
    sensitivity_levels: list[str]
    recommendation_types: list[str]


# Known optional ORE playbook keys validated in _validate_playbooks when present
ORE_PLAYBOOK_OPTIONAL_KEYS = frozenset(
    {"opening_templates", "value_statements", "forbidden_phrases", "tone"}
)
