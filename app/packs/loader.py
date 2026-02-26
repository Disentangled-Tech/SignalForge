"""Pack loader — load pack config from packs/ directory (Issue #189, Plan Step 2.1, #172)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
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
) -> str:
    """Compute SHA-256 hash of normalized pack config (Issue #190, Phase 3).

    Returns deterministic hex digest for config drift detection.
    """
    canonical = json.dumps(
        {
            "manifest": manifest,
            "taxonomy": taxonomy,
            "scoring": scoring,
            "esl_policy": esl_policy,
            "derivers": derivers,
            "playbooks": playbooks,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class Pack:
    """Loaded pack config with taxonomy, scoring, esl_policy, playbooks, derivers (Issue #172)."""

    manifest: dict
    taxonomy: dict
    scoring: dict
    esl_policy: dict
    playbooks: dict
    derivers: dict
    config_checksum: str


def _packs_root() -> Path:
    """Return path to packs/ directory (project root / packs)."""
    # app/packs/loader.py -> project_root/packs
    app_dir = Path(__file__).resolve().parent.parent
    return app_dir.parent / "packs"


def get_pack_dir(pack_id: str) -> Path:
    """Return path to pack directory packs/{pack_id}/ (M4 prompt bundles).

    Does not require the directory to exist. Use for resolving pack prompts
    when pack has schema_version \"2\".
    """
    if not pack_id or not isinstance(pack_id, str):
        raise ValueError("pack_id must be a non-empty string")
    if not _PACK_ID_PATTERN.match(pack_id):
        raise ValueError(f"pack_id must match [a-zA-Z0-9_-]+ (got {pack_id!r})")
    if ".." in pack_id or "/" in pack_id or "\\" in pack_id:
        raise ValueError("pack_id must not contain path separators or '..'")
    return _packs_root() / pack_id


def load_pack(pack_id: str, version: str) -> Pack:
    """Load pack config from packs/{pack_id}/ directory.

    For schema_version "2" (Pack v2, Issue #285 M5): taxonomy.yaml and derivers.yaml
    are optional; if absent, empty dicts are used and derive uses core derivers.
    scoring.yaml and esl_policy.yaml are always required.

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
    # scoring.yaml and esl_policy.yaml remain required for all packs.
    taxonomy_path = pack_dir / "taxonomy.yaml"
    if taxonomy_path.exists():
        with taxonomy_path.open() as f:
            taxonomy = yaml.safe_load(f) or {}
    elif is_v2:
        taxonomy = {}
    else:
        raise FileNotFoundError(f"taxonomy.yaml not found: {taxonomy_path}")

    scoring_path = pack_dir / "scoring.yaml"
    if not scoring_path.exists():
        raise FileNotFoundError(f"scoring.yaml not found: {scoring_path}")
    with scoring_path.open() as f:
        scoring = yaml.safe_load(f) or {}

    esl_path = pack_dir / "esl_policy.yaml"
    if not esl_path.exists():
        raise FileNotFoundError(f"esl_policy.yaml not found: {esl_path}")
    with esl_path.open() as f:
        esl_policy = yaml.safe_load(f) or {}

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
    )

    return Pack(
        manifest=manifest,
        taxonomy=taxonomy,
        scoring=scoring,
        esl_policy=esl_policy,
        playbooks=playbooks_dict,
        derivers=derivers,
        config_checksum=config_checksum,
    )
