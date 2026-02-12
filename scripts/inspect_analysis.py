#!/usr/bin/env python3
"""Inspect stored analysis and pain_signals for a company.

Usage:
    python scripts/inspect_analysis.py [company_id]
    python scripts/inspect_analysis.py   # lists all companies with analysis

Helps debug why CTO score might be zero.
"""

from __future__ import annotations

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.analysis_record import AnalysisRecord
from app.models.company import Company


def main() -> None:
    db = SessionLocal()
    try:
        if len(sys.argv) > 1:
            company_id = int(sys.argv[1])
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                print(f"Company {company_id} not found")
                return
            analyses = (
                db.query(AnalysisRecord)
                .filter(AnalysisRecord.company_id == company_id)
                .order_by(AnalysisRecord.created_at.desc())
                .limit(3)
                .all()
            )
            print(f"\nCompany: {company.name} (id={company_id})")
            print(f"  cto_need_score: {company.cto_need_score}")
            print(f"  current_stage: {company.current_stage}")
            print(f"\nLatest analysis records:")
            for a in analyses:
                print(f"\n  Analysis id={a.id} stage={a.stage!r} created={a.created_at}")
                pain = a.pain_signals_json or {}
                sigs = pain.get("signals", pain)
                print(f"  pain_signals_json keys: {list(pain.keys())}")
                if sigs:
                    print(f"  signals (first 3):")
                    for k, v in list(sigs.items())[:3]:
                        val = v.get("value") if isinstance(v, dict) else v
                        print(f"    {k}: value={val!r} (type={type(val).__name__})")
        else:
            companies = (
                db.query(Company)
                .join(AnalysisRecord, Company.id == AnalysisRecord.company_id)
                .distinct()
                .all()
            )
            print("\nCompanies with analysis:")
            for c in companies:
                latest = (
                    db.query(AnalysisRecord)
                    .filter(AnalysisRecord.company_id == c.id)
                    .order_by(AnalysisRecord.created_at.desc())
                    .first()
                )
                pain = (latest.pain_signals_json or {}).get("signals", {}) if latest else {}
                sample = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in list(pain.items())[:2]}
                print(f"  id={c.id} {c.name}: score={c.cto_need_score} stage={latest.stage if latest else '-'} sample={sample}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
