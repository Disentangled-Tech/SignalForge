#!/usr/bin/env python3
"""Run nightly TRS scoring job locally (Issue #91, #104).

Usage:
    python scripts/run_score_nightly.py
    uv run python scripts/run_score_nightly.py

Scores all companies with SignalEvents in last 365 days or on watchlist.
Writes readiness snapshots and engagement snapshots.
Exits 0 on success, 1 on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.services.readiness.score_nightly import run_score_nightly


def main() -> int:
    db = SessionLocal()
    try:
        result = run_score_nightly(db)
        print(
            f"status={result['status']} "
            f"job_run_id={result['job_run_id']} "
            f"companies_scored={result['companies_scored']} "
            f"companies_skipped={result['companies_skipped']}"
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
