"""Pack loader — load pack config from packs/ directory (Issue #189, Plan Step 2.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Pack:
    """Loaded pack config with taxonomy, scoring, esl_policy, playbooks."""

    manifest: dict
    taxonomy: dict
    scoring: dict
    esl_policy: dict
    playbooks: dict


def _packs_root() -> Path:
    """Return path to packs/ directory (project root / packs)."""
    # app/packs/loader.py -> project_root/packs
    app_dir = Path(__file__).resolve().parent.parent
    return app_dir.parent / "packs"


def load_pack(pack_id: str, version: str) -> Pack:
    """Load pack config from packs/{pack_id}/ directory.

    Args:
        pack_id: Pack identifier (e.g. 'fractional_cto_v1').
        version: Pack version (e.g. '1').

    Returns:
        Pack with taxonomy, scoring, esl_policy, playbooks.

    Raises:
        FileNotFoundError: Pack directory or required file not found.
        ValueError: Invalid pack_id or version.
    """
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

    taxonomy_path = pack_dir / "taxonomy.yaml"
    if not taxonomy_path.exists():
        raise FileNotFoundError(f"taxonomy.yaml not found: {taxonomy_path}")
    with taxonomy_path.open() as f:
        taxonomy = yaml.safe_load(f) or {}

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

    playbooks_dir = pack_dir / "playbooks"
    playbooks: dict = {}
    if playbooks_dir.is_dir():
        for p in playbooks_dir.glob("*.yaml"):
            with p.open() as f:
                playbooks[p.stem] = yaml.safe_load(f) or {}

    return Pack(
        manifest=manifest,
        taxonomy=taxonomy,
        scoring=scoring,
        esl_policy=esl_policy,
        playbooks=playbooks,
    )
