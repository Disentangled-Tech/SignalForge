"""Pack schema validation (Issue #172).

Validates pack manifest, taxonomy, scoring, esl_policy, derivers, and playbooks
for cross-reference consistency. Raises ValidationError on invalid config.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


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
) -> None:
    """Validate pack config for required fields and cross-references.

    Args:
        manifest: pack.json content
        taxonomy: taxonomy.yaml content
        scoring: scoring.yaml content
        esl_policy: esl_policy.yaml content
        derivers: derivers.yaml content
        playbooks: dict of playbook name -> content

    Raises:
        ValidationError: When validation fails, with a clear message.
    """
    _validate_manifest(manifest)
    signal_ids = _validate_taxonomy(taxonomy)
    _validate_scoring(scoring, signal_ids)
    _validate_derivers(derivers, signal_ids)
    _validate_esl_policy(esl_policy, signal_ids)


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
