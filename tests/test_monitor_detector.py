"""Tests for monitor detector (M3): detect_change."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.monitor.detector import detect_change
from app.schemas.monitor import ChangeEvent, SnapshotLike


def _snap(content_text: str, content_hash: str, fetched_at: datetime | None = None) -> SnapshotLike:
    return SnapshotLike(
        content_text=content_text,
        content_hash=content_hash,
        fetched_at=fetched_at or datetime.now(UTC),
    )


class TestDetectChangeNoPreviousSnapshot:
    """When there is no previous snapshot, no change event is emitted."""

    def test_get_latest_returns_none(self):
        def get_latest(company_id: int, url: str) -> SnapshotLike | None:
            return None

        result = detect_change(
            company_id=1,
            page_url="https://example.com/blog",
            current_text="Some content",
            current_hash="abc123",
            fetched_at=datetime.now(UTC),
            get_latest_snapshot=get_latest,
        )
        assert result is None

    def test_get_latest_called_with_company_id_and_url(self):
        get_latest = MagicMock(return_value=None)
        detect_change(
            company_id=42,
            page_url="https://example.com/careers",
            current_text="Jobs",
            current_hash="h1",
            fetched_at=datetime.now(UTC),
            get_latest_snapshot=get_latest,
        )
        get_latest.assert_called_once_with(42, "https://example.com/careers")


class TestDetectChangeHashUnchanged:
    """When current content hash equals previous snapshot hash, no change event."""

    def test_same_hash_returns_none(self):
        get_latest = MagicMock(return_value=_snap("Same content", "samehash", datetime.now(UTC)))
        result = detect_change(
            company_id=1,
            page_url="https://example.com/blog",
            current_text="Same content",
            current_hash="samehash",
            fetched_at=datetime.now(UTC),
            get_latest_snapshot=get_latest,
        )
        assert result is None

    def test_same_hash_different_text_still_returns_none(self):
        # Detector uses hash for quick path; if hashes match we skip diff
        get_latest = MagicMock(return_value=_snap("Content A", "hash1", datetime.now(UTC)))
        result = detect_change(
            company_id=1,
            page_url="https://example.com/p",
            current_text="Content B",
            current_hash="hash1",  # same hash as previous
            fetched_at=datetime.now(UTC),
            get_latest_snapshot=get_latest,
        )
        assert result is None


class TestDetectChangeContentChanged:
    """When current content hash differs from previous, a ChangeEvent is returned."""

    def test_returns_change_event(self):
        get_latest = MagicMock(return_value=_snap("Old text\n", "oldhash", datetime.now(UTC)))
        result = detect_change(
            company_id=1,
            page_url="https://example.com/blog",
            current_text="New text\n",
            current_hash="newhash",
            fetched_at=datetime(2025, 3, 2, 12, 0, 0, tzinfo=UTC),
            get_latest_snapshot=get_latest,
        )
        assert result is not None
        assert isinstance(result, ChangeEvent)
        assert result.page_url == "https://example.com/blog"
        assert result.timestamp == datetime(2025, 3, 2, 12, 0, 0, tzinfo=UTC)
        assert result.before_hash == "oldhash"
        assert result.after_hash == "newhash"
        assert len(result.diff_summary) > 0
        assert len(result.diff_summary) <= 2000

    def test_diff_summary_reflects_change(self):
        get_latest = MagicMock(return_value=_snap("Before\n", "h1", datetime.now(UTC)))
        result = detect_change(
            company_id=1,
            page_url="https://example.com/p",
            current_text="After\n",
            current_hash="h2",
            fetched_at=datetime.now(UTC),
            get_latest_snapshot=get_latest,
        )
        assert result is not None
        assert (
            "Before" in result.diff_summary
            or "After" in result.diff_summary
            or "+" in result.diff_summary
            or "-" in result.diff_summary
            or "line" in result.diff_summary.lower()
        )

    def test_snippet_before_and_after_optional(self):
        get_latest = MagicMock(return_value=_snap("Old\n", "o", datetime.now(UTC)))
        result = detect_change(
            company_id=1,
            page_url="https://example.com/p",
            current_text="New\n",
            current_hash="n",
            fetched_at=datetime.now(UTC),
            get_latest_snapshot=get_latest,
        )
        assert result is not None
        # Snippets may or may not be set by detector (plan says optional)
        assert hasattr(result, "snippet_before")
        assert hasattr(result, "snippet_after")
