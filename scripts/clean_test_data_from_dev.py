#!/usr/bin/env python3
"""
One-time cleanup script to remove test data from signalforge_dev.

Removes:
- Users where username LIKE 'integration_test_%'
- Companies where domain/website_url contains 'example.com' OR name contains ' co' OR any
  field contains 'test' (name, domain, website_url, founder_name, founder_linkedin_url,
  company_linkedin_url, source, alignment_notes, current_stage, notes). CASCADE removes children.

Requires --confirm to actually delete. Refuses to run if DATABASE_URL points to signalforge_test.
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env from project root (same as app)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from sqlalchemy.orm import sessionmaker

# Company deletion: example.com OR any text field contains 'test' OR name contains ' co'
_COMPANY_WHERE = """
    domain LIKE '%example.com' OR website_url LIKE '%example.com'
    OR name ILIKE '% co%'
    OR name ILIKE '%test%'
    OR COALESCE(domain, '') ILIKE '%test%'
    OR COALESCE(website_url, '') ILIKE '%test%'
    OR COALESCE(founder_name, '') ILIKE '%test%'
    OR COALESCE(founder_linkedin_url, '') ILIKE '%test%'
    OR COALESCE(company_linkedin_url, '') ILIKE '%test%'
    OR COALESCE(source, '') ILIKE '%test%'
    OR COALESCE(alignment_notes, '') ILIKE '%test%'
    OR COALESCE(current_stage, '') ILIKE '%test%'
    OR COALESCE(notes, '') ILIKE '%test%'
"""


def _extract_db_name(url: str) -> str:
    """Extract database name from PostgreSQL URL."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    dbname = path.lstrip("/").split("?")[0] or ""
    return dbname


def _get_database_url(database_arg: str | None) -> str:
    """Resolve database URL from env or --database flag."""
    if database_arg:
        # User provided explicit database name; build URL from env components
        user = os.getenv("PGUSER") or os.getenv("USER") or "postgres"
        password = os.getenv("PGPASSWORD", "")
        host = os.getenv("PGHOST", "localhost")
        port = os.getenv("PGPORT", "5432")
        return (
            f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database_arg}"
        )
    raw = os.getenv("DATABASE_URL")
    if not raw:
        sys.exit("Error: DATABASE_URL not set. Set it or use --database <dbname>")
    if raw.startswith("postgresql://") and "postgresql+psycopg" not in raw:
        raw = raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove test data (integration_test_* users; example.com, ' co' in name, or 'test' in any field companies) from dev DB."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually perform deletions. Without this, only prints counts.",
    )
    parser.add_argument(
        "--database",
        metavar="DBNAME",
        help="Override: use this database name (builds URL from PG* env vars).",
    )
    args = parser.parse_args()

    url = _get_database_url(args.database)
    dbname = _extract_db_name(url)

    if dbname == "signalforge_test":
        sys.exit(
            "Error: Refusing to run against signalforge_test. "
            "Use signalforge_dev. Unset DATABASE_URL or set DATABASE_URL to dev."
        )

    engine = create_engine(url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with Session() as session:
        # Count before
        users_count = session.execute(
            text("SELECT COUNT(*) FROM users WHERE username LIKE 'integration_test_%'")
        ).scalar()
        companies_count = session.execute(
            text(f"SELECT COUNT(*) FROM companies WHERE {_COMPANY_WHERE}")
        ).scalar()

        print(f"Database: {dbname}")
        print(f"Users (integration_test_*): {users_count}")
        print(f"Companies (example.com, ' co' in name, or 'test' in any field): {companies_count}")

        if users_count == 0 and companies_count == 0:
            print("No test data to remove.")
            return

        if not args.confirm:
            print("\nDry run. Use --confirm to perform deletions.")
            return

        # Delete users first (no FK to companies)
        if users_count > 0:
            session.execute(
                text("DELETE FROM users WHERE username LIKE 'integration_test_%'")
            )
            print(f"Deleted {users_count} user(s).")

        # Delete companies (CASCADE removes BriefingItems, ReadinessSnapshots, etc.)
        if companies_count > 0:
            session.execute(text(f"DELETE FROM companies WHERE {_COMPANY_WHERE}"))
            print(f"Deleted {companies_count} company(ies).")

        session.commit()

    # Verify after
    with Session() as session:
        users_after = session.execute(
            text("SELECT COUNT(*) FROM users WHERE username LIKE 'integration_test_%'")
        ).scalar()
        companies_after = session.execute(
            text(f"SELECT COUNT(*) FROM companies WHERE {_COMPANY_WHERE}")
        ).scalar()
        print(f"\nAfter: users={users_after}, companies={companies_after}")


if __name__ == "__main__":
    main()
