"""Unit tests for monitor snapshot store (M2, Issue #280)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.company import Company
from app.monitor.snapshot_store import get_latest_snapshot, save_snapshot


@pytest.fixture
def company_with_website(db: Session) -> Company:
    c = Company(name="Monitor Test Co", website_url="https://monitor.example.com")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


class TestSaveAndGetSnapshot:
    def test_save_then_get_returns_same_content(self, db: Session, company_with_website: Company):
        save_snapshot(
            db,
            company_id=company_with_website.id,
            url="https://monitor.example.com/blog",
            content_text="Blog content here",
            source_type="blog",
        )
        snap = get_latest_snapshot(db, company_with_website.id, "https://monitor.example.com/blog")
        assert snap is not None
        assert snap.content_text == "Blog content here"
        assert snap.source_type == "blog"

    def test_get_latest_none_when_no_snapshot(self, db: Session, company_with_website: Company):
        assert (
            get_latest_snapshot(db, company_with_website.id, "https://other.example.com/") is None
        )

    def test_save_updates_existing_latest_wins(self, db: Session, company_with_website: Company):
        url = "https://monitor.example.com/careers"
        save_snapshot(db, company_with_website.id, url, "First content", source_type="careers")
        save_snapshot(db, company_with_website.id, url, "Second content", source_type="careers")
        snap = get_latest_snapshot(db, company_with_website.id, url)
        assert snap is not None
        assert snap.content_text == "Second content"
