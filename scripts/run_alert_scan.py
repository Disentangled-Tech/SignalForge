#!/usr/bin/env python3
"""Run daily readiness delta alert scan locally (Issue #92).

Usage:
    python scripts/run_alert_scan.py
    uv run python scripts/run_alert_scan.py

Run after score_nightly. Creates alerts when |delta| >= ALERT_DELTA_THRESHOLD.
Exits 0 on success, 1 on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.services.readiness.alert_scan import run_alert_scan


def main() -> int:
    db = SessionLocal()
    try:
        result = run_alert_scan(db)
        print(
            f"status={result['status']} "
            f"alerts_created={result['alerts_created']} "
            f"companies_scanned={result['companies_scanned']}"
        )
        return 0 if result["status"] == "completed" else 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
