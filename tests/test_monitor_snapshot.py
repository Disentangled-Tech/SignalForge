"""Tests for monitor page snapshot storage (M2: Diff-Based Monitor Engine)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.models import Company
from app.monitor.snapshot_store import get_latest_snapshot, save_snapshot


def test_save_snapshot_stores_row(db: Session) -> None:
    """save_snapshot persists a page_snapshots row with given fields."""
    company = Company(name="SnapshotCo", website_url="https://snap.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    url = "https://snap.example.com/blog"
    content_text = "Hello world"
    content_hash = "a" * 64
    fetched_at = datetime.now(UTC)

    row = save_snapshot(
        db,
        company_id=company.id,
        url=url,
        content_text=content_text,
        content_hash=content_hash,
        fetched_at=fetched_at,
    )
    db.commit()

    assert row is not None
    assert row.id is not None
    assert row.company_id == company.id
    assert row.url == url
    assert row.content_text == content_text
    assert row.content_hash == content_hash
    assert row.fetched_at == fetched_at
    assert row.source_type is None


def test_save_snapshot_with_source_type(db: Session) -> None:
    """save_snapshot accepts optional source_type (blog, careers, press, etc.)."""
    company = Company(name="SourceTypeCo", website_url="https://src.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    row = save_snapshot(
        db,
        company_id=company.id,
        url="https://src.example.com/careers",
        content_text="We are hiring",
        content_hash="b" * 64,
        fetched_at=datetime.now(UTC),
        source_type="careers",
    )
    db.commit()

    assert row is not None
    assert row.source_type == "careers"


def test_save_snapshot_content_text_nullable(db: Session) -> None:
    """save_snapshot allows content_text=None for large pages."""
    company = Company(name="NullTextCo", website_url="https://null.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    row = save_snapshot(
        db,
        company_id=company.id,
        url="https://null.example.com/press",
        content_text=None,
        content_hash="c" * 64,
        fetched_at=datetime.now(UTC),
    )
    db.commit()

    assert row is not None
    assert row.content_text is None
    assert row.content_hash == "c" * 64


def test_get_latest_snapshot_returns_saved(db: Session) -> None:
    """get_latest_snapshot returns the snapshot after save_snapshot."""
    company = Company(name="GetLatestCo", website_url="https://get.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    url = "https://get.example.com/blog"
    content_text = "Latest content"
    content_hash = "d" * 64
    fetched_at = datetime.now(UTC)

    save_snapshot(
        db,
        company_id=company.id,
        url=url,
        content_text=content_text,
        content_hash=content_hash,
        fetched_at=fetched_at,
    )
    db.commit()

    latest = get_latest_snapshot(db, company_id=company.id, url=url)
    assert latest is not None
    assert latest.content_hash == content_hash
    assert latest.content_text == content_text


def test_get_latest_snapshot_returns_none_when_empty(db: Session) -> None:
    """get_latest_snapshot returns None when no snapshot for (company_id, url)."""
    company = Company(name="EmptyCo", website_url="https://empty.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    latest = get_latest_snapshot(db, company_id=company.id, url="https://empty.example.com/missing")
    assert latest is None


def test_get_latest_snapshot_returns_most_recent_by_fetched_at(db: Session) -> None:
    """When multiple snapshots exist for same (company_id, url), get_latest returns latest by fetched_at."""
    company = Company(name="MultiCo", website_url="https://multi.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    url = "https://multi.example.com/docs"
    base = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

    save_snapshot(
        db,
        company_id=company.id,
        url=url,
        content_text="v1",
        content_hash="e1" + "0" * 62,
        fetched_at=base,
    )
    save_snapshot(
        db,
        company_id=company.id,
        url=url,
        content_text="v2",
        content_hash="e2" + "0" * 62,
        fetched_at=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
    )
    db.commit()

    latest = get_latest_snapshot(db, company_id=company.id, url=url)
    assert latest is not None
    assert latest.content_hash == "e2" + "0" * 62
    assert latest.content_text == "v2"


def test_get_latest_snapshot_ignores_other_company(db: Session) -> None:
    """get_latest_snapshot only returns snapshot for the given company_id."""
    c1 = Company(name="C1", website_url="https://c1.example.com")
    c2 = Company(name="C2", website_url="https://c2.example.com")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    url = "https://shared.example.com/page"
    save_snapshot(
        db,
        company_id=c1.id,
        url=url,
        content_text="C1 content",
        content_hash="f1" + "0" * 62,
        fetched_at=datetime.now(UTC),
    )
    db.commit()

    latest_c1 = get_latest_snapshot(db, company_id=c1.id, url=url)
    latest_c2 = get_latest_snapshot(db, company_id=c2.id, url=url)

    assert latest_c1 is not None
    assert latest_c1.content_text == "C1 content"
    assert latest_c2 is None


@pytest.mark.integration
def test_snapshot_store_integration_rollback(db: Session) -> None:
    """Integration: save and get work with real DB; test isolation via rollback."""
    company = Company(name="IntegrationCo", website_url="https://int.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    save_snapshot(
        db,
        company_id=company.id,
        url="https://int.example.com/changelog",
        content_text="Changelog v1",
        content_hash="ff" * 32,
        fetched_at=datetime.now(UTC),
        source_type="docs",
    )
    db.commit()

    latest = get_latest_snapshot(db, company_id=company.id, url="https://int.example.com/changelog")
    assert latest is not None
    assert latest.source_type == "docs"
    # db fixture rolls back after test; no persistent pollution
