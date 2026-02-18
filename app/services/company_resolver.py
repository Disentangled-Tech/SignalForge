"""Company resolver for entity resolution and deduplication (Issue #88)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.company_alias import CompanyAlias
from app.schemas.company import CompanyCreate


# Suffixes to strip when normalizing company names (case-insensitive)
_NAME_SUFFIXES = ("inc", "llc", "ltd", "corp", "corporation", "co", "company")


def normalize_name(name: str) -> str:
    """Normalize company name for comparison.

    - Lowercase, strip
    - Remove common suffixes: inc, llc, ltd, corp, co, company
    - Remove punctuation, collapse whitespace
    """
    if not name or not name.strip():
        return ""
    s = name.strip().lower()
    # Remove punctuation first so "Inc." and "Inc" both match
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Repeatedly remove suffixes (handles "Beta Corp, LLC" -> "beta")
    prev = None
    while prev != s:
        prev = s
        for suffix in _NAME_SUFFIXES:
            pattern = re.compile(rf"\s+{re.escape(suffix)}\s*$", re.IGNORECASE)
            s = pattern.sub("", s).strip()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_domain(url: str) -> str | None:
    """Extract domain from URL, strip www, return lowercase.

    Returns None if URL is invalid.
    """
    if not url or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
        if not parsed.netloc:
            return None
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        # Strip standard ports (443, 80) for consistent domain matching
        if ":" in host:
            hostname, port = host.rsplit(":", 1)
            if port in ("443", "80"):
                host = hostname
        return host if host else None
    except Exception:
        return None


def resolve_or_create_company(db: Session, data: CompanyCreate) -> tuple[Company, bool]:
    """Resolve to existing company or create new one.

    Resolution order (per v2-spec Section 10):
    1. Domain match (Company.domain or CompanyAlias alias_type='domain')
    2. Website host match (extract_domain from website_url)
    3. LinkedIn match (exact URL or CompanyAlias alias_type='social')
    4. Fuzzy name match (normalize_name) — only when no domain/URL/LinkedIn

    Returns (company, created) where created is True if a new company was inserted.
    """
    domain = extract_domain(data.website_url) if data.website_url else None
    linkedin = (data.company_linkedin_url or "").strip() or None
    norm_name = normalize_name(data.company_name) if data.company_name else ""

    # 1. Domain match
    if domain:
        existing = db.query(Company).filter(Company.domain == domain).first()
        if existing:
            return existing, False
        alias_match = (
            db.query(Company)
            .join(CompanyAlias)
            .filter(
                CompanyAlias.alias_type == "domain",
                CompanyAlias.alias_value == domain,
            )
            .first()
        )
        if alias_match:
            return alias_match, False

    # 2. Website host match (compare extracted domain from existing companies)
    if domain:
        for c in db.query(Company).filter(Company.website_url.isnot(None)).all():
            if c.website_url and extract_domain(c.website_url) == domain:
                return c, False

    # 3. LinkedIn match
    if linkedin:
        existing = db.query(Company).filter(
            Company.company_linkedin_url == linkedin
        ).first()
        if existing:
            return existing, False
        alias_match = (
            db.query(Company)
            .join(CompanyAlias)
            .filter(
                CompanyAlias.alias_type == "social",
                CompanyAlias.alias_value == linkedin,
            )
            .first()
        )
        if alias_match:
            return alias_match, False

    # 4. Fuzzy name match — only when no domain/URL/LinkedIn to avoid false positives
    if norm_name and not domain and not linkedin:
        for c in db.query(Company).all():
            if normalize_name(c.name) == norm_name:
                return c, False

    # No match — create new company with aliases
    return _create_company_with_aliases(db, data, domain)


def _create_company_with_aliases(
    db: Session, data: CompanyCreate, domain: str | None
) -> tuple[Company, bool]:
    """Create a new company and its alias entries."""
    from app.services.company import _schema_to_model_data

    model_data = _schema_to_model_data(data)
    if domain is not None:
        model_data["domain"] = domain

    company = Company(**model_data)
    db.add(company)
    db.flush()  # Get company.id before adding aliases

    aliases: list[tuple[str, str]] = []

    if data.company_name:
        norm = normalize_name(data.company_name)
        if norm:
            aliases.append(("name", norm))

    if domain:
        aliases.append(("domain", domain))

    if data.website_url:
        url_domain = extract_domain(data.website_url)
        if url_domain:
            aliases.append(("url", data.website_url.strip().lower()))

    if data.company_linkedin_url:
        linkedin = data.company_linkedin_url.strip()
        if linkedin:
            aliases.append(("social", linkedin))

    for alias_type, alias_value in aliases:
        db.add(
            CompanyAlias(
                company_id=company.id,
                alias_type=alias_type,
                alias_value=alias_value,
            )
        )

    db.commit()
    db.refresh(company)
    return company, True
