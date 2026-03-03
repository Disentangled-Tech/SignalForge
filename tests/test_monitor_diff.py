"""Unit tests for monitor diff (M3, Issue #280)."""

from __future__ import annotations

from app.monitor.diff import compute_diff


class TestComputeDiff:
    def test_no_change_returns_empty_diff_and_summary(self):
        text = "Hello world\nLine two\n"
        unified, summary = compute_diff(text, text)
        assert unified == ""
        assert "0 lines added, 0 removed" in summary

    def test_small_change_returns_unified_diff_and_summary(self):
        before = "Line one\nLine two\n"
        after = "Line one\nLine two changed\n"
        unified, summary = compute_diff(before, after)
        assert "Line two\n" in unified or "Line two changed" in unified
        assert "1 lines added, 1 removed" in summary or "1" in summary

    def test_large_change_includes_diff_length_in_summary(self):
        before = "x" * 1000
        after = "y" * 1000
        unified, summary = compute_diff(before, after)
        assert len(unified) > 500
        assert "diff length" in summary or "added" in summary.lower()

    def test_empty_previous(self):
        unified, summary = compute_diff("", "New content\n")
        assert "New content" in unified or "added" in summary.lower()
        assert isinstance(summary, str)
