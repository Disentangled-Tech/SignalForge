"""Watchlist model tests (Issue #83)."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Company, Watchlist


def test_watchlist_model_creation() -> None:
    """Model instantiates with all fields."""
    entry = Watchlist(
        company_id=1,
        added_reason="High readiness score",
        is_active=True,
    )
    assert entry.company_id == 1
    assert entry.added_reason == "High readiness score"
    assert entry.is_active is True
    # added_at is set on insert; before persist it may be None


def test_watchlist_duplicate_active_raises_integrity_error(db: Session) -> None:
    """Two active entries for same company raise IntegrityError."""
    company = Company(name="DupCo", website_url="https://dup.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    w1 = Watchlist(company_id=company.id, is_active=True)
    db.add(w1)
    db.commit()

    w2 = Watchlist(company_id=company.id, is_active=True)
    db.add(w2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_watchlist_soft_delete_allows_re_add(db: Session) -> None:
    """Set is_active=false, then add new active entry for same company."""
    company = Company(name="ReAddCo", website_url="https://readd.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    w1 = Watchlist(company_id=company.id, added_reason="First add", is_active=True)
    db.add(w1)
    db.commit()
    db.refresh(w1)

    w1.is_active = False
    db.commit()

    w2 = Watchlist(company_id=company.id, added_reason="Re-added", is_active=True)
    db.add(w2)
    db.commit()
    db.refresh(w2)

    assert w1.is_active is False
    assert w2.is_active is True
    assert w2.company_id == company.id


def test_watchlist_company_relationship(db: Session) -> None:
    """Company.watchlist_entries loads correctly."""
    company = Company(name="RelCo", website_url="https://rel.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    entry = Watchlist(company_id=company.id, added_reason="Watching", is_active=True)
    db.add(entry)
    db.commit()

    db.refresh(company)
    assert len(company.watchlist_entries) == 1
    assert company.watchlist_entries[0].company_id == company.id
    assert company.watchlist_entries[0].added_reason == "Watching"
