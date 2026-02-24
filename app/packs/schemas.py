"""Pack schema validation (Issue #172, #190).

Validates pack manifest, taxonomy, scoring, esl_policy, derivers, and playbooks
for cross-reference consistency. Raises ValidationError on invalid config.

Phase 1 (Issue #190): playbook refs, semver (optional), ethical gates.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.packs.ethical_constants import validate_esl_policy_against_core_bans

logger = logging.getLogger(__name__)

# Semver pattern: x.y.z where x,y,z are non-negative integers
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class ValidationError(Exception):
    """Raised when pack schema validation fails."""

    pass


def validate_pack_schema(
    manifest: dict[str, Any],
    taxonomy: dict[str, Any],
    scoring: dict[str, Any],
    esl_policy: dict[str, Any],
    derivers: dict[str, Any],
    playbooks: dict[str, Any],
    *,
    strict_explainability: bool = False,
    strict_semver: bool = False,
) -> None:
    """Validate pack config for required fields and cross-references.

    Args:
        manifest: pack.json content
        taxonomy: taxonomy.yaml content
        scoring: scoring.yaml content
        esl_policy: esl_policy.yaml content
        derivers: derivers.yaml content
        playbooks: dict of playbook name -> content
        strict_explainability: If True, require explainability_template per signal.
        strict_semver: If True, require version in x.y.z semver format.

    Raises:
        ValidationError: When validation fails, with a clear message.
    """
    _validate_manifest(manifest)
    if strict_semver:
        _validate_version_semver(manifest)
    signal_ids = _validate_taxonomy(taxonomy)
    if strict_explainability:
        _validate_explainability(taxonomy, signal_ids)
    _validate_scoring(scoring, signal_ids)
    _validate_derivers(derivers, signal_ids)
    _validate_esl_policy(esl_policy, signal_ids)
    _validate_playbooks(playbooks, taxonomy, esl_policy)
    _validate_ethical_policy(esl_policy)


def _validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate manifest has required fields: id, version, name, schema_version."""
    if not manifest:
        raise ValidationError("manifest is required and must not be empty")
    required = ("id", "version", "name", "schema_version")
    for key in required:
        if key not in manifest:
            raise ValidationError(f"manifest missing required field: {key}")
        val = manifest[key]
        if val is None or (isinstance(val, str) and not val.strip()):
            raise ValidationError(f"manifest field '{key}' must not be empty")


def _validate_taxonomy(taxonomy: dict[str, Any]) -> set[str]:
    """Validate taxonomy has non-empty signal_ids. Returns signal_ids set."""
    if not isinstance(taxonomy, dict):
        raise ValidationError("taxonomy must be a dict")
    ids = taxonomy.get("signal_ids")
    if ids is None:
        raise ValidationError("taxonomy must have signal_ids")
    if not isinstance(ids, list):
        raise ValidationError("taxonomy signal_ids must be a list")
    if len(ids) == 0:
        raise ValidationError("taxonomy signal_ids must not be empty")
    return {str(s) for s in ids if s is not None and str(s).strip()}


def _validate_scoring(scoring: dict[str, Any], signal_ids: set[str]) -> None:
    """Validate scoring base_scores reference only taxonomy signal_ids."""
    if not isinstance(scoring, dict):
        return
    base_scores = scoring.get("base_scores") or {}
    if not isinstance(base_scores, dict):
        return
    for dim_name, dim_scores in base_scores.items():
        if not isinstance(dim_scores, dict):
            continue
        for sig_id in dim_scores:
            if sig_id not in signal_ids:
                raise ValidationError(
                    f"scoring base_scores.{dim_name} references signal_id '{sig_id}' "
                    f"not in taxonomy.signal_ids"
                )


def _validate_derivers(derivers: dict[str, Any], signal_ids: set[str]) -> None:
    """Validate derivers passthrough signal_ids are in taxonomy."""
    if not isinstance(derivers, dict):
        raise ValidationError("derivers must be a dict")
    inner = derivers.get("derivers") or {}
    passthrough = inner.get("passthrough") if isinstance(inner, dict) else []
    if not isinstance(passthrough, list):
        return
    for i, entry in enumerate(passthrough):
        if not isinstance(entry, dict):
            continue
        if "signal_id" not in entry:
            raise ValidationError(
                f"derivers passthrough entry at index {i} missing required field 'signal_id'"
            )
        sid = entry.get("signal_id")
        if sid not in signal_ids:
            raise ValidationError(
                f"derivers passthrough references signal_id '{sid}' not in taxonomy.signal_ids"
            )


def _validate_esl_policy(esl_policy: dict[str, Any], signal_ids: set[str]) -> None:
    """Validate ESL svi_event_types reference taxonomy signal_ids when present."""
    if not isinstance(esl_policy, dict):
        return
    svi_types = esl_policy.get("svi_event_types")
    if not svi_types or not isinstance(svi_types, list):
        return
    for sig in svi_types:
        if sig not in signal_ids:
            raise ValidationError(
                f"esl_policy svi_event_types references '{sig}' not in taxonomy.signal_ids"
            )


def _validate_version_semver(manifest: dict[str, Any]) -> None:
    """Validate manifest version is semver format (x.y.z)."""
    version = manifest.get("version")
    if version is None:
        return
    version_str = str(version).strip()
    if not _SEMVER_PATTERN.match(version_str):
        raise ValidationError(
            f"manifest version must be semver format (x.y.z), got '{version}'"
        )


def _validate_explainability(taxonomy: dict[str, Any], signal_ids: set[str]) -> None:
    """Validate taxonomy has explainability_template for every signal_id."""
    if not isinstance(taxonomy, dict):
        return
    templates = taxonomy.get("explainability_templates")
    if templates is None:
        raise ValidationError(
            "taxonomy must have explainability_templates when strict_explainability=True"
        )
    if not isinstance(templates, dict):
        raise ValidationError("taxonomy explainability_templates must be a dict")
    missing = signal_ids - set(templates.keys())
    if missing:
        raise ValidationError(
            f"taxonomy explainability_templates missing for signal_ids: {sorted(missing)}"
        )
    for sid, tpl in templates.items():
        if not isinstance(tpl, str) or not tpl.strip():
            raise ValidationError(
                f"taxonomy explainability_templates['{sid}'] must be non-empty string"
            )


def _validate_playbooks(
    playbooks: dict[str, Any],
    taxonomy: dict[str, Any],
    esl_policy: dict[str, Any],
) -> None:
    """Validate playbooks reference valid sensitivity levels when present."""
    if not isinstance(playbooks, dict):
        return
    valid_recommendation_types: set[str] = set()
    boundaries = esl_policy.get("recommendation_boundaries") or []
    for b in boundaries:
        if isinstance(b, (list, tuple)) and len(b) >= 2:
            valid_recommendation_types.add(str(b[1]))
    if not valid_recommendation_types:
        return
    for name, content in playbooks.items():
        if not isinstance(content, dict):
            continue
        for key in ("sensitivity_levels", "recommendation_types"):
            refs = content.get(key)
            if refs is None:
                continue
            if not isinstance(refs, list):
                raise ValidationError(
                    f"playbook '{name}' {key} must be a list"
                )
            for ref in refs:
                if ref not in valid_recommendation_types:
                    raise ValidationError(
                        f"playbook '{name}' {key} references '{ref}' not in "
                        f"esl_policy recommendation_boundaries"
                    )


def _validate_ethical_policy(esl_policy: dict[str, Any]) -> None:
    """Validate esl_policy does not override core ethical bans (ADR-006)."""
    validate_esl_policy_against_core_bans(esl_policy)
