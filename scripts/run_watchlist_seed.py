#!/usr/bin/env python3
"""Run watchlist seed flow locally (Issue #279 M3).

Usage:
    python scripts/run_watchlist_seed.py <bundle_id> [bundle_id ...] [--workspace-id UUID] [--pack-id UUID]
    uv run python scripts/run_watchlist_seed.py <bundle_id> [bundle_id ...]

Orchestrates seed_from_bundles → run_deriver → run_score_nightly.
Exits 0 on success, 1 on failure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.services.watchlist_seeder import run_watchlist_seed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run watchlist seed: seed from bundles → derive → score (Issue #279 M3)",
    )
    parser.add_argument(
        "bundle_ids",
        nargs="+",
        metavar="BUNDLE_ID",
        help="Evidence bundle UUID(s) to seed from",
    )
    parser.add_argument(
        "--workspace-id",
        metavar="UUID",
        default=None,
        help="Workspace ID; uses default if omitted",
    )
    parser.add_argument(
        "--pack-id",
        metavar="UUID",
        default=None,
        help="Pack UUID; uses workspace active pack if omitted",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    bundle_uuids: list[UUID] = []
    for raw in args.bundle_ids:
        try:
            bundle_uuids.append(UUID(raw))
        except ValueError:
            print(f"Invalid bundle_id (must be UUID): {raw}", file=sys.stderr)
            return 1

    workspace_uuid: UUID | None = None
    if args.workspace_id:
        try:
            workspace_uuid = UUID(args.workspace_id)
        except ValueError:
            print(f"Invalid workspace_id (must be UUID): {args.workspace_id}", file=sys.stderr)
            return 1

    pack_uuid: UUID | None = None
    if args.pack_id:
        try:
            pack_uuid = UUID(args.pack_id)
        except ValueError:
            print(f"Invalid pack_id (must be UUID): {args.pack_id}", file=sys.stderr)
            return 1

    db = SessionLocal()
    try:
        result = run_watchlist_seed(
            db,
            bundle_ids=bundle_uuids,
            workspace_id=workspace_uuid,
            pack_id=pack_uuid,
        )
        seed = result.get("seed_result", {})
        derive = result.get("derive_result", {})
        score = result.get("score_result", {})
        print(
            f"status={result['status']} "
            f"events_stored={seed.get('events_stored', 0)} "
            f"instances_upserted={derive.get('instances_upserted', 0)} "
            f"companies_scored={score.get('companies_scored', 0)}"
        )
        if result.get("error"):
            print(f"error={result['error']}", file=sys.stderr)
        return 0 if result["status"] == "completed" else 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
