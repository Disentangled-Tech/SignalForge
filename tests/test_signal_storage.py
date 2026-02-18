"""Tests for signal storage service (dedup, store, last_scan_at)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.company import Company
from app.models.signal_record import SignalRecord
from app.services.signal_storage import _compute_hash, store_signal


# ── Helpers ──────────────────────────────────────────────────────────


def _make_company(id: int = 1, name: str = "Acme") -> MagicMock:
    c = MagicMock(spec=Company)
    c.id = id
    c.name = name
    c.website_url = "https://acme.example.com"
    c.last_scan_at = None
    return c


def _make_query_mock(existing_record=None, company=None):
    """Build a mock db.query() that handles SignalRecord and Company lookups."""
    db = MagicMock()

    def _query_side_effect(model):
        chain = MagicMock()
        if model is SignalRecord:
            chain.filter.return_value.first.return_value = existing_record
        elif model is Company:
            chain.filter.return_value.first.return_value = company
        return chain

    db.query.side_effect = _query_side_effect
    return db


# ── Tests ────────────────────────────────────────────────────────────


class TestComputeHash:
    def test_sha256(self):
        text = "hello world"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert _compute_hash(text) == expected

    def test_empty_string(self):
        assert _compute_hash("") == hashlib.sha256(b"").hexdigest()


class TestStoreSignal:
    def test_store_new_signal(self):
        """New content is saved and company.last_scan_at is updated."""
        company = _make_company()
        db = _make_query_mock(existing_record=None, company=company)

        result = store_signal(
            db,
            company_id=1,
            source_url="https://acme.example.com/blog",
            source_type="blog",
            content_text="Fresh content",
        )

        # A new SignalRecord should be added to the session
        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert isinstance(added, SignalRecord)
        assert added.company_id == 1
        assert added.source_type == "blog"
        assert added.content_hash == _compute_hash("Fresh content")

        # last_scan_at should have been set
        assert company.last_scan_at is not None

        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    def test_duplicate_signal_skipped(self):
        """Same company_id + content_hash → return None, no add. No commit when company missing."""
        existing = MagicMock(spec=SignalRecord)
        existing.id = 99
        db = _make_query_mock(existing_record=existing, company=None)

        result = store_signal(
            db,
            company_id=1,
            source_url="https://acme.example.com/blog",
            source_type="blog",
            content_text="Duplicate content",
        )

        assert result is None
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_duplicate_signal_updates_last_scan_at(self):
        """Duplicate signal still updates company.last_scan_at (AC #14: last activity timestamp)."""
        company = _make_company()
        company.last_scan_at = None
        existing = MagicMock(spec=SignalRecord)
        existing.id = 99
        db = _make_query_mock(existing_record=existing, company=company)

        result = store_signal(
            db,
            company_id=1,
            source_url="https://acme.example.com/blog",
            source_type="blog",
            content_text="Duplicate content",
        )

        assert result is None
        db.add.assert_not_called()
        assert company.last_scan_at is not None
        db.commit.assert_called_once()

    def test_last_scan_at_updated(self):
        """company.last_scan_at is set to roughly now on new signal."""
        company = _make_company()
        assert company.last_scan_at is None

        db = _make_query_mock(existing_record=None, company=company)
        before = datetime.now(timezone.utc)

        store_signal(
            db,
            company_id=1,
            source_url="https://acme.example.com",
            source_type="homepage",
            content_text="Some text",
        )

        after = datetime.now(timezone.utc)
        assert company.last_scan_at is not None
        assert before <= company.last_scan_at <= after

    def test_company_not_found_still_stores(self):
        """If company row is missing, signal is still stored (no crash)."""
        db = _make_query_mock(existing_record=None, company=None)

        store_signal(
            db,
            company_id=999,
            source_url="https://ghost.example.com",
            source_type="homepage",
            content_text="Orphan signal",
        )

        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_store_signal_persists_raw_html_when_provided(self):
        """When raw_html is provided, it is persisted on the SignalRecord."""
        company = _make_company()
        db = _make_query_mock(existing_record=None, company=company)

        result = store_signal(
            db,
            company_id=1,
            source_url="https://acme.example.com",
            source_type="homepage",
            content_text="Extracted text",
            raw_html="<html><body><p>Raw HTML content</p></body></html>",
        )

        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert isinstance(added, SignalRecord)
        assert added.raw_html == "<html><body><p>Raw HTML content</p></body></html>"

    def test_store_signal_accepts_none_raw_html(self):
        """When raw_html is None (default), record is stored without raw_html (backward compat)."""
        company = _make_company()
        db = _make_query_mock(existing_record=None, company=company)

        store_signal(
            db,
            company_id=1,
            source_url="https://acme.example.com",
            source_type="homepage",
            content_text="Some text",
        )

        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert isinstance(added, SignalRecord)
        assert added.raw_html is None

