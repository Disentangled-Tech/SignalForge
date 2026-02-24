"""CLI to validate all packs in packs/ directory (Issue #190, Phase 4).

Usage:
    python -m app.packs.validate_all_packs

Exits 0 if all packs validate; exits 1 on first failure.
Packs in EXCLUDE_PACK_IDS are skipped (test fixtures that intentionally fail).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Packs intentionally invalid (test fixtures): skip in CI validation.
EXCLUDE_PACK_IDS: frozenset[str] = frozenset({"invalid_schema_pack"})


def _packs_root() -> Path:
    """Return path to packs/ directory (project root / packs)."""
    app_dir = Path(__file__).resolve().parent.parent
    return app_dir.parent / "packs"


def validate_all_packs() -> int:
    """Load and validate each pack in packs/ and return exit code.

    Returns:
        0 if all packs validate; 1 if any pack fails.
    """
    from app.packs.loader import load_pack
    from app.packs.schemas import ValidationError

    root = _packs_root()
    if not root.is_dir():
        print(f"ERROR: packs directory not found: {root}", file=sys.stderr)
        return 1

    failed = 0
    validated = 0

    for pack_dir in sorted(root.iterdir()):
        if not pack_dir.is_dir():
            continue
        pack_json = pack_dir / "pack.json"
        if not pack_json.exists():
            continue

        with pack_json.open() as f:
            manifest = json.load(f)
        pack_id = manifest.get("id")
        version = manifest.get("version")

        if pack_id is None or version is None:
            print(f"ERROR: {pack_dir.name}/pack.json missing id or version", file=sys.stderr)
            failed += 1
            continue

        if pack_id in EXCLUDE_PACK_IDS:
            print(f"SKIP: {pack_id} (excluded test fixture)")
            continue

        try:
            pack = load_pack(pack_id, str(version))
            print(f"OK: {pack_id} v{version} (checksum={pack.config_checksum[:8]}...)")
            validated += 1
        except ValidationError as e:
            print(f"FAIL: {pack_id} v{version} - {e}", file=sys.stderr)
            failed += 1
        except (FileNotFoundError, ValueError) as e:
            print(f"FAIL: {pack_id} v{version} - {e}", file=sys.stderr)
            failed += 1

    if failed > 0:
        print(f"\n{failed} pack(s) failed validation.", file=sys.stderr)
        return 1
    print(f"\nAll {validated} pack(s) validated successfully.")
    return 0


def main() -> None:
    """Entry point for python -m app.packs.validate_all_packs."""
    sys.exit(validate_all_packs())


if __name__ == "__main__":
    main()
