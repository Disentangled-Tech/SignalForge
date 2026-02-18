"""Create a company record for SignalForge.

Usage:
    python -m app.scripts.create_company --company-name "Acme Corp" [--website-url URL] [--founder-name NAME] ...
"""

from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal
from app.schemas.company import CompanyCreate
from app.services.company import _model_to_read
from app.services.company_resolver import resolve_or_create_company


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a SignalForge company")
    parser.add_argument(
        "--company-name",
        required=True,
        help="Company name (required)",
    )
    parser.add_argument("--website-url", default=None, help="Company website URL")
    parser.add_argument("--founder-name", default=None, help="Founder name")
    parser.add_argument(
        "--founder-linkedin-url",
        default=None,
        help="Founder LinkedIn profile URL",
    )
    parser.add_argument(
        "--company-linkedin-url",
        default=None,
        help="Company LinkedIn page URL",
    )
    parser.add_argument("--notes", default=None, help="Notes about the company")
    args = parser.parse_args()

    name = args.company_name.strip()
    if not name:
        print("Error: company name cannot be empty.")
        sys.exit(1)

    db = SessionLocal()
    try:
        data = CompanyCreate(
            company_name=name,
            website_url=args.website_url.strip() if args.website_url else None,
            founder_name=args.founder_name.strip() if args.founder_name else None,
            founder_linkedin_url=(
                args.founder_linkedin_url.strip()
                if args.founder_linkedin_url
                else None
            ),
            company_linkedin_url=(
                args.company_linkedin_url.strip()
                if args.company_linkedin_url
                else None
            ),
            notes=args.notes.strip() if args.notes else None,
        )
        company, created = resolve_or_create_company(db, data)
        if not created:
            print(f"Company '{name}' already exists (id={company.id}).")
            sys.exit(1)
        read = _model_to_read(company)
        print(f"Company '{read.company_name}' created successfully (id={read.id}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
