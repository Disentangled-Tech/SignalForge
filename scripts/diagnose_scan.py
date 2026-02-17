#!/usr/bin/env python3
"""Diagnose why a company scan fails.

Usage:
    python scripts/diagnose_scan.py <company_id>
    # or with uv:
    uv run python scripts/diagnose_scan.py <company_id>

Prints a report of fetch attempts for the company's website_url and common paths,
with success/failure status and error details.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy.orm import Session
from urllib.parse import urljoin

from app.db.session import SessionLocal
from app.models.company import Company
from app.services.extractor import extract_text
from app.services.fetcher import USER_AGENT, TIMEOUT, MAX_REDIRECTS
from app.services.page_discovery import COMMON_PATHS, MIN_TEXT_LENGTH


def _normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


async def _fetch_with_diagnostics(url: str) -> tuple[bool, str | None, str]:
    """Fetch URL and return (success, html_or_none, message)."""
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return True, response.text, f"HTTP {response.status_code}"
    except httpx.TimeoutException as e:
        return False, None, f"Timeout: {e}"
    except httpx.ConnectError as e:
        return False, None, f"Connection error: {e}"
    except httpx.HTTPStatusError as e:
        return False, None, f"HTTP {e.response.status_code} for {e.request.url}"
    except httpx.HTTPError as e:
        return False, None, f"HTTP error: {e}"


async def diagnose(company_id: int) -> None:
    db: Session = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if company is None:
            print(f"Company {company_id} not found.")
            return
        if not company.website_url:
            print(f"Company {company_id} ({company.name}) has no website_url.")
            return

        base_url = _normalize_url(company.website_url)
        urls_to_try = [base_url] + [
            urljoin(base_url + "/", p.lstrip("/")) for p in COMMON_PATHS
        ]

        print(f"\nDiagnosing scan for: {company.name} (id={company_id})")
        print(f"website_url (stored): {company.website_url!r}")
        print(f"website_url (normalized): {base_url}")
        print("Note: Scan uses only website_url. LinkedIn URLs are not fetched.")
        print(f"User-Agent: {USER_AGENT}")
        print("-" * 60)

        success_count = 0
        for url in urls_to_try:
            ok, html, msg = await _fetch_with_diagnostics(url)
            if ok and html:
                text = extract_text(html)
                passed = len(text) > MIN_TEXT_LENGTH
                status = "OK" if passed else "SKIP (text too short)"
                print(f"  {url}")
                print(f"    -> {status} | len={len(text)} chars (min {MIN_TEXT_LENGTH})")
                if passed:
                    success_count += 1
            else:
                print(f"  {url}")
                print(f"    -> FAIL | {msg}")
            print()

        print("-" * 60)
        print(f"Result: {success_count}/{len(urls_to_try)} pages would produce signals.")
        if success_count == 0:
            print("\nPossible causes:")
            print("  - User-Agent blocked (try a browser-like User-Agent)")
            print("  - Site requires JavaScript (SPA)")
            print("  - Rate limiting / IP blocking")
            print("  - SSL/certificate issues")
            print("  - Wrong URL format")

    finally:
        db.close()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnose_scan.py <company_id>")
        sys.exit(1)
    try:
        company_id = int(sys.argv[1])
    except ValueError:
        print("company_id must be an integer")
        sys.exit(1)

    asyncio.run(diagnose(company_id))


if __name__ == "__main__":
    main()
