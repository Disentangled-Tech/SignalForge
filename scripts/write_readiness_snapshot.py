#!/usr/bin/env python3
"""Write a ReadinessSnapshot row (Issue #82 verification script).

Usage:
    python scripts/write_readiness_snapshot.py
    # or with uv:
    uv run python scripts/write_readiness_snapshot.py

Creates or fetches a company, inserts a sample ReadinessSnapshot, and prints it.
Exits 0 on success.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models import Company, ReadinessSnapshot


def main() -> int:
    db = SessionLocal()
    try:
        # Create or fetch a company
        company = db.query(Company).filter(Company.name == "ReadinessSnapshotTestCo").first()
        if not company:
            company = Company(
                name="ReadinessSnapshotTestCo",
                website_url="https://readiness-test.example.com",
            )
            db.add(company)
            db.commit()
            db.refresh(company)
            print(f"Created company id={company.id} name={company.name}")
        else:
            print(f"Using existing company id={company.id} name={company.name}")

        # Insert a sample ReadinessSnapshot
        as_of = date.today()
        explain_payload = {
            "weights": {"M": 0.30, "C": 0.30, "P": 0.25, "G": 0.15},
            "dimensions": {"M": 70, "C": 60, "P": 55, "G": 40, "R": 62},
            "top_events": [
                {
                    "event_type": "funding_raised",
                    "event_time": "2026-02-01T00:00:00Z",
                    "source": "crunchbase",
                    "contribution_points": 35,
                    "confidence": 0.9,
                }
            ],
            "suppressors_applied": [],
        }

        snapshot = ReadinessSnapshot(
            company_id=company.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=62,
            explain=explain_payload,
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        print(f"Wrote ReadinessSnapshot id={snapshot.id}")
        print(f"  company_id={snapshot.company_id} as_of={snapshot.as_of}")
        print(f"  momentum={snapshot.momentum} complexity={snapshot.complexity}")
        print(f"  pressure={snapshot.pressure} leadership_gap={snapshot.leadership_gap}")
        print(f"  composite={snapshot.composite}")
        print(f"  explain keys={list(snapshot.explain.keys()) if snapshot.explain else None}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
