"""Tests for company resolver and entity resolution (Issue #88)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.company_alias import CompanyAlias
from app.schemas.company import CompanyCreate
from app.services.company_resolver import (
    extract_domain,
    normalize_company_input,
    normalize_name,
    resolve_or_create_company,
)

# ── normalize_name tests ─────────────────────────────────────────────


class TestNormalizeName:
    def test_removes_inc_suffix(self) -> None:
        assert normalize_name("Acme Inc.") == "acme"
        assert normalize_name("Acme Inc") == "acme"

    def test_removes_llc_suffix(self) -> None:
        assert normalize_name("Beta Corp, LLC") == "beta"  # Corp and LLC both stripped
        assert normalize_name("Beta LLC") == "beta"

    def test_removes_ltd_suffix(self) -> None:
        assert normalize_name("Foo Ltd") == "foo"
        assert normalize_name("Foo Ltd.") == "foo"

    def test_removes_corp_suffix(self) -> None:
        assert normalize_name("Gamma Corp") == "gamma"

    def test_removes_co_suffix(self) -> None:
        assert normalize_name("Delta Co") == "delta"

    def test_removes_company_suffix(self) -> None:
        assert normalize_name("Foo Bar Company") == "foo bar"

    def test_collapses_whitespace(self) -> None:
        assert normalize_name("  Foo   Bar  ") == "foo bar"

    def test_removes_punctuation(self) -> None:
        assert normalize_name("Acme, Inc.") == "acme"
        assert normalize_name("Beta-Corp") == "beta"  # Corp suffix stripped

    def test_empty_string(self) -> None:
        assert normalize_name("") == ""
        assert normalize_name("   ") == ""

    def test_unicode(self) -> None:
        # Basic unicode handling - strip and lowercase
        result = normalize_name("Café Inc.")
        assert "café" in result or "cafe" in result


# ── extract_domain tests ──────────────────────────────────────────────


class TestExtractDomain:
    def test_extracts_domain_from_https(self) -> None:
        assert extract_domain("https://www.foo.com/path") == "foo.com"
        assert extract_domain("https://foo.com") == "foo.com"

    def test_strips_www(self) -> None:
        assert extract_domain("https://www.example.com") == "example.com"
        assert extract_domain("http://www.bar.com/") == "bar.com"

    def test_returns_lowercase(self) -> None:
        assert extract_domain("https://WWW.FOO.COM") == "foo.com"

    def test_invalid_url_returns_none(self) -> None:
        assert extract_domain("not-a-url") is None
        assert extract_domain("") is None

    def test_url_with_port(self) -> None:
        # Standard ports (443, 80) are stripped for domain matching
        result = extract_domain("https://foo.com:443/path")
        assert result == "foo.com"


# ── normalize_company_input tests (pure, no DB) ───────────────────────


class TestNormalizeCompanyInput:
    """Pure unit tests for normalize_company_input — no DB dependency."""

    def test_returns_domain_from_website_url(self) -> None:
        data = CompanyCreate(
            company_name="Acme Inc",
            website_url="https://www.acme.com/about",
        )
        result = normalize_company_input(data)
        assert result["domain"] == "acme.com"
        assert result["norm_name"] == "acme"
        assert result["linkedin"] is None

    def test_returns_norm_name_from_company_name(self) -> None:
        data = CompanyCreate(
            company_name="Beta Corp, LLC",
            website_url=None,
        )
        result = normalize_company_input(data)
        assert result["domain"] is None
        assert result["norm_name"] == "beta"
        assert result["linkedin"] is None

    def test_returns_linkedin_stripped(self) -> None:
        data = CompanyCreate(
            company_name="LinkedIn Co",
            website_url=None,
            company_linkedin_url="  https://linkedin.com/company/foo  ",
        )
        result = normalize_company_input(data)
        assert result["domain"] is None
        assert result["norm_name"] == "linkedin"  # "Co" suffix stripped
        assert result["linkedin"] == "https://linkedin.com/company/foo"

    def test_empty_linkedin_becomes_none(self) -> None:
        data = CompanyCreate(
            company_name="Foo",
            company_linkedin_url="   ",
        )
        result = normalize_company_input(data)
        assert result["linkedin"] is None

    def test_all_fields_populated(self) -> None:
        data = CompanyCreate(
            company_name="Gamma Inc",
            website_url="https://gamma.io",
            company_linkedin_url="https://linkedin.com/company/gamma",
        )
        result = normalize_company_input(data)
        assert result["domain"] == "gamma.io"
        assert result["norm_name"] == "gamma"
        assert result["linkedin"] == "https://linkedin.com/company/gamma"

    def test_whitespace_only_company_name_yields_empty_norm_name(self) -> None:
        data = CompanyCreate(
            company_name="   ",
            website_url=None,
        )
        result = normalize_company_input(data)
        assert result["norm_name"] == ""


# ── resolve_or_create_company tests ──────────────────────────────────


@pytest.fixture
def clean_db(db: Session) -> Session:
    """DB session with companies cleared for resolver integration tests."""
    db.query(CompanyAlias).delete()
    db.query(Company).delete()
    db.commit()
    return db


class TestResolveOrCreateCompany:
    """Integration-style tests using real DB session from conftest."""

    def test_two_urls_same_domain_resolve_to_one(
        self, clean_db: Session
    ) -> None:
        """Two URLs with same domain should resolve to one company."""
        data_a = CompanyCreate(
            company_name="DomainTest Inc",
            website_url="https://domaintest.com",
        )
        company_a, created_a = resolve_or_create_company(clean_db, data_a)
        assert created_a is True
        assert company_a.name == "DomainTest Inc"
        assert company_a.domain == "domaintest.com"

        data_b = CompanyCreate(
            company_name="DomainTest LLC",
            website_url="https://www.domaintest.com/about",
        )
        company_b, created_b = resolve_or_create_company(clean_db, data_b)
        assert created_b is False
        assert company_b.id == company_a.id
        assert company_b.name == "DomainTest Inc"

    # TODO(flaky): Intermittent deadlock when run in parallel; consider isolating
    # or fixing DELETE ordering to avoid ShareLock contention across processes.
    def test_inc_vs_llc_variants_resolve_to_one(
        self, clean_db: Session
    ) -> None:
        """Inc vs LLC name variants (no URL) should resolve to same company."""
        data_a = CompanyCreate(company_name="NameVariant Inc")
        company_a, created_a = resolve_or_create_company(clean_db, data_a)
        assert created_a is True

        data_b = CompanyCreate(company_name="NameVariant LLC")
        company_b, created_b = resolve_or_create_company(clean_db, data_b)
        assert created_b is False
        assert company_b.id == company_a.id

    def test_different_domains_create_two_companies(
        self, clean_db: Session
    ) -> None:
        """Different domains should create different companies."""
        data_a = CompanyCreate(
            company_name="DomainAlpha Corp",
            website_url="https://domain-alpha-88.com",
        )
        company_a, created_a = resolve_or_create_company(clean_db, data_a)
        assert created_a is True

        data_b = CompanyCreate(
            company_name="DomainBeta Corp",
            website_url="https://domain-beta-88.com",
        )
        company_b, created_b = resolve_or_create_company(clean_db, data_b)
        assert created_b is True
        assert company_b.id != company_a.id

    def test_no_domain_name_match_only_resolves(
        self, clean_db: Session
    ) -> None:
        """When no domain/URL/LinkedIn, name match only (current behavior)."""
        data_a = CompanyCreate(company_name="NameMatch Foo Bar Company")
        company_a, created_a = resolve_or_create_company(clean_db, data_a)
        assert created_a is True

        data_b = CompanyCreate(company_name="NameMatch Foo Bar")
        company_b, created_b = resolve_or_create_company(clean_db, data_b)
        assert created_b is False
        assert company_b.id == company_a.id

    def test_linkedin_match_resolves(
        self, clean_db: Session
    ) -> None:
        """LinkedIn URL match should resolve to existing company."""
        linkedin_url = "https://linkedin.com/company/linkedin-test-unique-88"
        data_a = CompanyCreate(
            company_name="LinkedInTest Co",
            company_linkedin_url=linkedin_url,
        )
        company_a, created_a = resolve_or_create_company(clean_db, data_a)
        assert created_a is True

        data_b = CompanyCreate(
            company_name="LinkedInTest Inc",
            company_linkedin_url=linkedin_url,
        )
        company_b, created_b = resolve_or_create_company(clean_db, data_b)
        assert created_b is False
        assert company_b.id == company_a.id
