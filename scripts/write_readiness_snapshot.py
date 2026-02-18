#!/usr/bin/env python3
"""Write a ReadinessSnapshot row (Issue #82, #87 verification script).

Usage:
    python scripts/write_readiness_snapshot.py
    python scripts/write_readiness_snapshot.py --use-engine  # use engine when events exist
    uv run python scripts/write_readiness_snapshot.py

When --use-engine: seeds SignalEvents if none exist, then calls write_readiness_snapshot.
Otherwise: inserts a hardcoded sample ReadinessSnapshot (legacy behavior).
Exits 0 on success.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models import Company, ReadinessSnapshot, SignalEvent
from app.services.readiness.snapshot_writer import write_readiness_snapshot


def _seed_sample_events(db, company_id: int) -> None:
    """Seed sample SignalEvents for testing the engine."""
    now = datetime.now(timezone.utc)
    events = [
        SignalEvent(
            company_id=company_id,
            source="script",
            event_type="funding_raised",
            event_time=now - timedelta(days=5),
            confidence=0.9,
        ),
        SignalEvent(
            company_id=company_id,
            source="script",
            event_type="api_launched",
            event_time=now - timedelta(days=30),
            confidence=0.8,
        ),
        SignalEvent(
            company_id=company_id,
            source="script",
            event_type="enterprise_customer",
            event_time=now - timedelta(days=10),
            confidence=0.85,
        ),
    ]
    for ev in events:
        db.add(ev)
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Write ReadinessSnapshot")
    parser.add_argument(
        "--use-engine",
        action="store_true",
        help="Use write_readiness_snapshot (seeds events if none exist)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
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

        as_of = date.today()

        if args.use_engine:
            # Seed events if none exist
            event_count = db.query(SignalEvent).filter(SignalEvent.company_id == company.id).count()
            if event_count == 0:
                _seed_sample_events(db, company.id)
                print("Seeded sample SignalEvents")
            snapshot = write_readiness_snapshot(db, company.id, as_of)
            if snapshot is None:
                print("No SignalEvents found; run with --use-engine after seeding")
                return 1
        else:
            # Legacy: hardcoded sample
            explain_payload = {
                "weights": {"M": 0.30, "C": 0.30, "P": 0.25, "G": 0.15},
                "dimensions": {"M": 70, "C": 60, "P": 55, "G": 40, "R": 59},
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
                composite=59,
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
