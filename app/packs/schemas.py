"""Pack schema validation (Issue #172, #190).

Validates pack manifest, taxonomy, scoring, esl_policy, derivers, and playbooks
for cross-reference consistency. Raises ValidationError on invalid config.

Phase 1 (Issue #190): playbook refs, semver (optional), ethical gates.
Phase 2 (Issue #190): regex safety validation for derivers (ADR-008).
Pack v2 (M2, M5): For schema_version "2", allowed signal_ids come from core
taxonomy; scoring/ESL/derivers are validated against core only. Taxonomy may
be minimal (labels/explainability only) or empty; empty derivers skip validation.
See docs/pack_v2_contract.md for the v2 contract.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core_taxonomy.loader import get_core_signal_ids
from app.packs.ethical_constants import validate_esl_policy_against_core_bans
from app.packs.regex_validator import validate_deriver_regex_safety

logger = logging.getLogger(__name__)

# Semver pattern: x.y.z where x,y,z are non-negative integers
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

# Allowed source_fields for pattern derivers (SignalEvent string attributes only).
# Excludes raw (JSONB) and non-string fields (ADR-008 defense in depth).
# Includes: title, summary, url, source.
ALLOWED_PATTERN_SOURCE_FIELDS: frozenset[str] = frozenset({
    "title",
    "summary",
    "url",
    "source",
})


class ValidationError(Exception):
    """Raised when pack schema validation fails."""

    pass


def get_schema_version(manifest: dict[str, Any]) -> str:
    """Return pack schema version from manifest (Pack v2 contract).

    When schema_version is missing or empty, returns "1". Used by validation
    and loader to branch behavior for v2 (core signal_ids, optional taxonomy/derivers).
    """
    val = manifest.get("schema_version")
    if val is None:
        return "1"
    if isinstance(val, str) and val.strip():
        return val.strip()
    return "1"


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
        manifest: pack.json content (schema_version optional; default "1").
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
    signal_ids = _validate_taxonomy(manifest, taxonomy)
    if strict_explainability:
        _validate_explainability(taxonomy, signal_ids)
    _validate_scoring(scoring, signal_ids)
    _validate_derivers(derivers, signal_ids, manifest)
    validate_deriver_regex_safety(derivers)
    _validate_esl_policy(esl_policy, signal_ids)
    _validate_playbooks(playbooks, taxonomy, esl_policy)
    _validate_ethical_policy(esl_policy)


def _validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate manifest has required fields: id, version, name.

    schema_version is optional (default "1", see get_schema_version). If present,
    it must be a non-empty string.
    """
    if not manifest:
        raise ValidationError("manifest is required and must not be empty")
    required = ("id", "version", "name")
    for key in required:
        if key not in manifest:
            raise ValidationError(f"manifest missing required field: {key}")
        val = manifest[key]
        if val is None or (isinstance(val, str) and not val.strip()):
            raise ValidationError(f"manifest field '{key}' must not be empty")
    # schema_version optional; when present must be non-empty
    sv = manifest.get("schema_version")
    if sv is not None and (not isinstance(sv, str) or not sv.strip()):
        raise ValidationError("manifest field 'schema_version' when present must be non-empty")


def _get_allowed_signal_ids(manifest: dict[str, Any], taxonomy: dict[str, Any]) -> set[str]:
    """Return allowed signal_ids for scoring/ESL/derivers validation (Pack v2 M2).

    For schema_version "2": returns core taxonomy signal_ids (pack may omit
    signal_ids or have labels/explainability only). For schema_version "1":
    returns pack taxonomy signal_ids (taxonomy must have non-empty signal_ids).
    """
    if manifest.get("schema_version") == "2":
        return set(get_core_signal_ids())
    ids = taxonomy.get("signal_ids")
    if ids is None or not isinstance(ids, list) or len(ids) == 0:
        raise ValidationError("taxonomy must have non-empty signal_ids (schema_version 1)")
    return {str(s) for s in ids if s is not None and str(s).strip()}


def _validate_taxonomy(manifest: dict[str, Any], taxonomy: dict[str, Any]) -> set[str]:
    """Validate taxonomy and return allowed signal_ids set for cross-ref validation.

    schema_version "2": taxonomy must be a dict; signal_ids optional (labels/
    explainability only). Returns core signal_ids. schema_version "1": requires
    non-empty taxonomy.signal_ids; returns pack signal_ids.
    """
    if not isinstance(taxonomy, dict):
        raise ValidationError("taxonomy must be a dict")
    return _get_allowed_signal_ids(manifest, taxonomy)


def _validate_scoring(scoring: dict[str, Any], signal_ids: set[str]) -> None:
    """Validate scoring base_scores, decay, and suppressors when present (Issue #174)."""
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

    # Optional: validate decay structure when present
    decay = scoring.get("decay")
    if decay is not None and isinstance(decay, dict):
        for dim in ("momentum", "pressure", "complexity"):
            d = decay.get(dim)
            if d is None:
                continue
            if not isinstance(d, dict):
                raise ValidationError(
                    f"scoring decay.{dim} must be a dict of range keys to numeric values"
                )
            for key, val in d.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValidationError(
                        f"scoring decay.{dim} keys must be non-empty strings (e.g. '0-30', '91+')"
                    )
                if not isinstance(val, (int, float)):
                    raise ValidationError(
                        f"scoring decay.{dim}['{key}'] must be numeric, got {type(val).__name__}"
                    )

    # Optional: validate suppressors when present
    suppressors = scoring.get("suppressors")
    if suppressors is not None and isinstance(suppressors, dict):
        for key in ("cto_hired_60_days", "cto_hired_180_days"):
            val = suppressors.get(key)
            if val is None:
                continue
            if not isinstance(val, (int, float)) or val < 0:
                raise ValidationError(
                    f"scoring suppressors.{key} must be non-negative number, got {val!r}"
                )

    # Optional: validate recommendation_bands when present (Issue #242)
    bands = scoring.get("recommendation_bands")
    if bands is not None and isinstance(bands, dict):
        for key in ("ignore_max", "watch_max", "high_priority_min"):
            val = bands.get(key)
            if val is None:
                continue
            if not isinstance(val, (int, float)) or val < 0:
                raise ValidationError(
                    f"scoring recommendation_bands.{key} must be non-negative number, got {val!r}"
                )
        ig = bands.get("ignore_max")
        wm = bands.get("watch_max")
        hp = bands.get("high_priority_min")
        if ig is not None and wm is not None and hp is not None:
            if not (ig < wm < hp):
                raise ValidationError(
                    "scoring recommendation_bands must satisfy ignore_max < watch_max < high_priority_min"
                )


def _validate_derivers(
    derivers: dict[str, Any],
    signal_ids: set[str],
    manifest: dict[str, Any],
) -> None:
    """Validate derivers passthrough and pattern signal_ids are in allowed set.

    Pack structure: derivers must be under the "derivers" key, e.g.:
      derivers:
        passthrough: [...]
        pattern: [...]

    For schema_version "2": if derivers absent or empty (no passthrough/pattern),
    skip validation. Otherwise validate against allowed signal_ids (core).
    Pattern source_fields (when present) must be a subset of allowed fields:
    title, summary, url, source.
    """
    if not isinstance(derivers, dict):
        raise ValidationError("derivers must be a dict")
    inner = derivers.get("derivers") or {}
    if not isinstance(inner, dict):
        return
    passthrough = inner.get("passthrough") or []
    pattern_list = inner.get("pattern") or []
    if manifest.get("schema_version") == "2" and not passthrough and not pattern_list:
        return

    # Passthrough derivers
    if isinstance(passthrough, list):
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

    # Pattern derivers (Phase 1, Issue #173)
    if isinstance(pattern_list, list):
        for i, entry in enumerate(pattern_list):
            if not isinstance(entry, dict):
                continue
            if "signal_id" not in entry:
                raise ValidationError(
                    f"derivers pattern entry at index {i} missing required field 'signal_id'"
                )
            if "pattern" not in entry and "regex" not in entry:
                raise ValidationError(
                    f"derivers pattern entry at index {i} must have 'pattern' or 'regex'"
                )
            sid = entry.get("signal_id")
            if sid not in signal_ids:
                raise ValidationError(
                    f"derivers pattern references signal_id '{sid}' not in taxonomy.signal_ids"
                )
            # Whitelist source_fields (defense in depth, ADR-008)
            source_fields = entry.get("source_fields")
            if source_fields is not None and isinstance(source_fields, list):
                for j, field in enumerate(source_fields):
                    if field not in ALLOWED_PATTERN_SOURCE_FIELDS:
                        raise ValidationError(
                            f"derivers pattern entry at index {i} source_fields[{j}] "
                            f"'{field}' not allowed; must be one of "
                            f"{sorted(ALLOWED_PATTERN_SOURCE_FIELDS)}"
                        )


def _validate_esl_policy(esl_policy: dict[str, Any], signal_ids: set[str]) -> None:
    """Validate ESL svi_event_types and Issue #175 keys reference taxonomy signal_ids when present."""
    if not isinstance(esl_policy, dict):
        return
    svi_types = esl_policy.get("svi_event_types")
    # Use pass (not return): when svi_event_types is empty/absent, skip svi validation
    # but continue to validate Issue #175 keys (blocked_signals, prohibited_combinations, etc.)
    if not svi_types or not isinstance(svi_types, list):
        pass
    else:
        for sig in svi_types:
            if sig not in signal_ids:
                raise ValidationError(
                    f"esl_policy svi_event_types references '{sig}' not in taxonomy.signal_ids"
                )

    # Issue #175: blocked_signals, sensitivity_mapping, prohibited_combinations, downgrade_rules
    blocked = esl_policy.get("blocked_signals")
    if blocked is not None and isinstance(blocked, list):
        for sig in blocked:
            if sig not in signal_ids:
                raise ValidationError(
                    f"esl_policy blocked_signals references '{sig}' not in taxonomy.signal_ids"
                )

    sensitivity = esl_policy.get("sensitivity_mapping")
    if sensitivity is not None and isinstance(sensitivity, dict):
        for sig in sensitivity:
            if sig not in signal_ids:
                raise ValidationError(
                    f"esl_policy sensitivity_mapping references '{sig}' not in taxonomy.signal_ids"
                )

    prohibited = esl_policy.get("prohibited_combinations")
    if prohibited is not None and isinstance(prohibited, list):
        for i, pair in enumerate(prohibited):
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                raise ValidationError(
                    f"esl_policy prohibited_combinations[{i}] must be a pair [signal_id, signal_id]"
                )
            a, b = str(pair[0]), str(pair[1])
            if a not in signal_ids:
                raise ValidationError(
                    f"esl_policy prohibited_combinations[{i}] references '{a}' not in taxonomy.signal_ids"
                )
            if b not in signal_ids:
                raise ValidationError(
                    f"esl_policy prohibited_combinations[{i}] references '{b}' not in taxonomy.signal_ids"
                )

    downgrade = esl_policy.get("downgrade_rules")
    if downgrade is not None and isinstance(downgrade, list):
        valid_recommendation_types = _valid_recommendation_types_from_esl(esl_policy)
        for i, rule in enumerate(downgrade):
            if not isinstance(rule, dict):
                raise ValidationError(
                    f"esl_policy downgrade_rules[{i}] must be a dict with trigger_signal and max_recommendation"
                )
            trigger = rule.get("trigger_signal")
            max_rec = rule.get("max_recommendation")
            if not trigger:
                raise ValidationError(
                    f"esl_policy downgrade_rules[{i}] missing required field 'trigger_signal'"
                )
            if trigger not in signal_ids:
                raise ValidationError(
                    f"esl_policy downgrade_rules[{i}] trigger_signal '{trigger}' not in taxonomy.signal_ids"
                )
            if max_rec:
                if not valid_recommendation_types:
                    raise ValidationError(
                        f"esl_policy downgrade_rules[{i}] max_recommendation requires "
                        f"recommendation_boundaries to be defined and non-empty"
                    )
                if max_rec not in valid_recommendation_types:
                    raise ValidationError(
                        f"esl_policy downgrade_rules[{i}] max_recommendation '{max_rec}' not in "
                        f"recommendation_boundaries"
                    )


def _valid_recommendation_types_from_esl(esl_policy: dict[str, Any]) -> set[str]:
    """Extract valid recommendation types from esl_policy recommendation_boundaries."""
    boundaries = esl_policy.get("recommendation_boundaries") or []
    valid: set[str] = set()
    for b in boundaries:
        if isinstance(b, (list, tuple)) and len(b) >= 2:
            valid.add(str(b[1]))
    return valid


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
