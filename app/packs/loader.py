"""Pack loader — load pack config from packs/ directory (Issue #189, Plan Step 2.1, #172)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.packs.schemas import ValidationError, validate_pack_schema

logger = logging.getLogger(__name__)

# Pack identifiers: alphanumeric, underscore, hyphen only. Prevents path traversal.
_PACK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_pack_id(pack_id: str, version: str) -> None:
    """Validate pack_id and version to prevent path traversal (Issue #189, Plan Step 4).

    Raises ValueError if pack_id or version contain path separators or other unsafe chars.
    """
    if not pack_id or not isinstance(pack_id, str):
        raise ValueError("pack_id must be a non-empty string")
    if not version or not isinstance(version, str):
        raise ValueError("version must be a non-empty string")
    if "\0" in pack_id or "\0" in version:
        raise ValueError("pack_id and version must not contain null bytes")
    if ".." in pack_id or ".." in version:
        raise ValueError("pack_id and version must not contain '..'")
    if "/" in pack_id or "\\" in pack_id or "/" in version or "\\" in version:
        raise ValueError("pack_id and version must not contain path separators")
    if not _PACK_ID_PATTERN.match(pack_id):
        raise ValueError(f"pack_id must match [a-zA-Z0-9_-]+ (got {pack_id!r})")
    if not _PACK_ID_PATTERN.match(version):
        raise ValueError(f"version must match [a-zA-Z0-9_-]+ (got {version!r})")


def compute_pack_config_checksum(
    manifest: dict[str, Any],
    taxonomy: dict[str, Any],
    scoring: dict[str, Any],
    esl_policy: dict[str, Any],
    derivers: dict[str, Any],
    playbooks: dict[str, Any],
    prompt_bundles: dict[str, Any] | None = None,
) -> str:
    """Compute SHA-256 hash of normalized pack config (Issue #190, Phase 3).

    Returns deterministic hex digest for config drift detection.
    Pack v2 (M1): prompt_bundles included when present.
    """
    payload: dict[str, Any] = {
        "manifest": manifest,
        "taxonomy": taxonomy,
        "scoring": scoring,
        "esl_policy": esl_policy,
        "derivers": derivers,
        "playbooks": playbooks,
    }
    if prompt_bundles is not None:
        payload["prompt_bundles"] = prompt_bundles
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_prompt_bundles(pack_dir: Path) -> dict[str, Any]:
    """Load prompt_bundles/ for v2: system, templates, few_shot (Issue #288 M1)."""
    out: dict[str, Any] = {"system": None, "templates": {}, "few_shot": {}}
    pb = pack_dir / "prompt_bundles"
    if not pb.is_dir():
        return out
    for ext in (".txt", ".md"):
        system_file = pb / f"system{ext}"
        if system_file.exists():
            out["system"] = system_file.read_text(encoding="utf-8").strip()
            break
    templates_dir = pb / "templates"
    if templates_dir.is_dir():
        for f in templates_dir.glob("*.yaml"):
            with f.open() as fp:
                out["templates"][f.stem] = yaml.safe_load(fp) or {}
        for f in templates_dir.glob("*.jinja2"):
            out["templates"][f.stem] = {"_raw": f.read_text(encoding="utf-8")}
    few_dir = pb / "few_shot"
    if few_dir.is_dir():
        for f in few_dir.glob("*.yaml"):
            with f.open() as fp:
                out["few_shot"][f.stem] = yaml.safe_load(fp) or {}
    return out


@dataclass
class Pack:
    """Loaded pack config with taxonomy, scoring, esl_policy, playbooks, derivers (Issue #172).

    Pack v2 (M1): prompt_bundles holds system/templates/few_shot when present.
    """

    manifest: dict
    taxonomy: dict
    scoring: dict
    esl_policy: dict
    playbooks: dict
    derivers: dict
    config_checksum: str
    prompt_bundles: dict = field(default_factory=dict)


def _packs_root() -> Path:
    """Return path to packs/ directory (project root / packs)."""
    # app/packs/loader.py -> project_root/packs
    app_dir = Path(__file__).resolve().parent.parent
    return app_dir.parent / "packs"


def load_pack(pack_id: str, version: str) -> Pack:
    """Load pack config from packs/{pack_id}/ directory.

    For schema_version "2" (Pack v2, Issue #285 M5): taxonomy.yaml and derivers.yaml
    are optional; if absent, empty dicts are used and derive uses core derivers.
    Validation for v2 uses core signal_ids (see app.packs.schemas). scoring.yaml
    and esl_policy.yaml are always required for all schema versions.

    Args:
        pack_id: Pack identifier (e.g. 'fractional_cto_v1').
        version: Pack version (e.g. '1').

    Returns:
        Pack with taxonomy, scoring, esl_policy, playbooks, derivers.

    Raises:
        FileNotFoundError: Pack directory or required file not found.
        ValueError: Invalid pack_id or version (e.g. path traversal attempt).
    """
    _validate_pack_id(pack_id, version)
    root = _packs_root()
    pack_dir = root / pack_id
    if not pack_dir.is_dir():
        raise FileNotFoundError(f"Pack directory not found: {pack_dir}")

    manifest_path = pack_dir / "pack.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"pack.json not found: {manifest_path}")

    with manifest_path.open() as f:
        manifest = json.load(f)

    if manifest.get("version") != version:
        raise ValueError(f"Pack {pack_id} version {manifest.get('version')} != requested {version}")

    is_v2 = manifest.get("schema_version") == "2"
    # For schema_version "2", taxonomy.yaml and derivers.yaml are optional (Issue #285 M5).
    # For v2 (M1): prefer analysis_weights.yaml / esl_rubric.yaml; fallback to scoring/esl_policy.
    taxonomy_path = pack_dir / "taxonomy.yaml"
    if taxonomy_path.exists():
        with taxonomy_path.open() as f:
            taxonomy = yaml.safe_load(f) or {}
    elif is_v2:
        taxonomy = {}
    else:
        raise FileNotFoundError(f"taxonomy.yaml not found: {taxonomy_path}")

    analysis_weights_path = pack_dir / "analysis_weights.yaml"
    scoring_path = pack_dir / "scoring.yaml"
    if is_v2 and analysis_weights_path.exists():
        with analysis_weights_path.open() as f:
            scoring = yaml.safe_load(f) or {}
    elif scoring_path.exists():
        with scoring_path.open() as f:
            scoring = yaml.safe_load(f) or {}
    else:
        raise FileNotFoundError(
            f"scoring.yaml or analysis_weights.yaml not found in {pack_dir}"
        )

    esl_rubric_path = pack_dir / "esl_rubric.yaml"
    esl_path = pack_dir / "esl_policy.yaml"
    if is_v2 and esl_rubric_path.exists():
        with esl_rubric_path.open() as f:
            esl_policy = yaml.safe_load(f) or {}
    elif esl_path.exists():
        with esl_path.open() as f:
            esl_policy = yaml.safe_load(f) or {}
    else:
        raise FileNotFoundError(
            f"esl_policy.yaml or esl_rubric.yaml not found in {pack_dir}"
        )

    derivers_path = pack_dir / "derivers.yaml"
    if derivers_path.exists():
        with derivers_path.open() as f:
            derivers = yaml.safe_load(f) or {}
    elif is_v2:
        derivers = {}
    else:
        raise FileNotFoundError(f"derivers.yaml not found: {derivers_path}")

    playbooks_dir = pack_dir / "playbooks"
    playbooks_dict: dict = {}
    if playbooks_dir.is_dir():
        for p in playbooks_dir.glob("*.yaml"):
            with p.open() as f:
                playbooks_dict[p.stem] = yaml.safe_load(f) or {}

    prompt_bundles_dict: dict = {}
    if is_v2:
        prompt_bundles_dict = _load_prompt_bundles(pack_dir)

    try:
        validate_pack_schema(
            manifest=manifest,
            taxonomy=taxonomy,
            scoring=scoring,
            esl_policy=esl_policy,
            derivers=derivers,
            playbooks=playbooks_dict,
        )
    except ValidationError as e:
        logger.warning("Pack %s v%s validation failed: %s", pack_id, version, e)
        raise

    config_checksum = compute_pack_config_checksum(
        manifest=manifest,
        taxonomy=taxonomy,
        scoring=scoring,
        esl_policy=esl_policy,
        derivers=derivers,
        playbooks=playbooks_dict,
        prompt_bundles=prompt_bundles_dict if is_v2 else None,
    )

    return Pack(
        manifest=manifest,
        taxonomy=taxonomy,
        scoring=scoring,
        esl_policy=esl_policy,
        playbooks=playbooks_dict,
        derivers=derivers,
        config_checksum=config_checksum,
        prompt_bundles=prompt_bundles_dict,
    )
