#!/usr/bin/env python3
"""Run daily signal aggregation job locally (Issue #246).

Usage:
    python scripts/run_daily_aggregation.py
    uv run python scripts/run_daily_aggregation.py
    make signals-daily

Orchestrates ingest → derive → score. Prints ranked companies to console.
Exits 0 on success, 1 on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.services.aggregation.daily_aggregation import run_daily_aggregation


def main() -> int:
    db = SessionLocal()
    try:
        result = run_daily_aggregation(db)
        print(
            f"status={result['status']} "
            f"job_run_id={result['job_run_id']} "
            f"inserted={result.get('ingest_result', {}).get('inserted', 0)} "
            f"companies_scored={result.get('score_result', {}).get('companies_scored', 0)} "
            f"ranked_count={result['ranked_count']}"
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
