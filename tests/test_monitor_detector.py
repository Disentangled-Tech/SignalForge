"""Unit tests for monitor detector (M3, Issue #280)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.company import Company
from app.monitor.detector import detect_change
from app.monitor.snapshot_store import save_snapshot


@pytest.fixture
def company_with_website(db: Session) -> Company:
    c = Company(name="Detector Test Co", website_url="https://detector.example.com")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


class TestDetectChange:
    def test_returns_none_when_no_previous_snapshot(
        self, db: Session, company_with_website: Company
    ):
        out = detect_change(
            db,
            company_with_website.id,
            "https://detector.example.com/",
            "Some current content",
        )
        assert out is None

    def test_returns_none_when_hash_unchanged(self, db: Session, company_with_website: Company):
        url = "https://detector.example.com/blog"
        text = "Same content"
        save_snapshot(db, company_with_website.id, url, text)
        out = detect_change(db, company_with_website.id, url, text)
        assert out is None

    def test_returns_change_event_when_content_changed(
        self, db: Session, company_with_website: Company
    ):
        url = "https://detector.example.com/press"
        save_snapshot(db, company_with_website.id, url, "Old content")
        out = detect_change(db, company_with_website.id, url, "New content")
        assert out is not None
        assert out.page_url == url
        assert out.company_id == company_with_website.id
        assert out.before_hash != out.after_hash
        assert "1 lines added, 1 removed" in out.diff_summary or "removed" in out.diff_summary
