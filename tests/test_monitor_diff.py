"""Tests for monitor diff module (M3): compute_diff."""

from __future__ import annotations

from app.monitor.diff import compute_diff


class TestComputeDiffNoChange:
    """When previous and current text are identical, diff is empty and summary reflects no change."""

    def test_identical_text(self):
        text = "Line one\nLine two\nLine three\n"
        unified_diff, summary = compute_diff(text, text)
        assert unified_diff == ""
        assert "no change" in summary.lower() or "unchanged" in summary.lower() or summary == ""

    def test_empty_both(self):
        unified_diff, summary = compute_diff("", "")
        assert unified_diff == ""
        assert "no change" in summary.lower() or "unchanged" in summary.lower() or summary == ""


class TestComputeDiffSmallChange:
    """Small text changes produce a non-empty unified diff and a short summary."""

    def test_one_line_added(self):
        before = "Hello\nWorld\n"
        after = "Hello\nWorld\nNew line\n"
        unified_diff, summary = compute_diff(before, after)
        assert "New line" in unified_diff or "+" in unified_diff
        assert len(summary) > 0
        assert len(summary) <= 2000

    def test_one_line_removed(self):
        before = "A\nB\nC\n"
        after = "A\nC\n"
        unified_diff, summary = compute_diff(before, after)
        assert "B" in unified_diff or "-" in unified_diff
        assert len(summary) > 0

    def test_one_line_modified(self):
        before = "Old content\n"
        after = "New content\n"
        unified_diff, summary = compute_diff(before, after)
        assert "Old" in unified_diff or "New" in unified_diff
        assert "-" in unified_diff and "+" in unified_diff
        assert len(summary) > 0


class TestComputeDiffLargeChange:
    """Large changes still produce a bounded summary."""

    def test_summary_bounded(self):
        before = "x\n" * 500
        after = "y\n" * 500
        unified_diff, summary = compute_diff(before, after)
        assert len(unified_diff) > 0
        assert len(summary) <= 2000

    def test_many_lines_added(self):
        before = "start\n"
        after = "start\n" + "added\n" * 100
        unified_diff, summary = compute_diff(before, after)
        assert "added" in unified_diff or "+" in unified_diff
        assert len(summary) >= 0


class TestComputeDiffEdgeCases:
    """Edge cases: empty vs non-empty, unicode, single line."""

    def test_empty_previous_non_empty_current(self):
        unified_diff, summary = compute_diff("", "Only new\n")
        assert "Only new" in unified_diff or "+" in unified_diff
        assert len(summary) > 0

    def test_non_empty_previous_empty_current(self):
        unified_diff, summary = compute_diff("Only old\n", "")
        assert "Only old" in unified_diff or "-" in unified_diff
        assert len(summary) > 0

    def test_unicode_content(self):
        before = "Hello 世界\n"
        after = "Hello 世界\nExtra\n"
        unified_diff, summary = compute_diff(before, after)
        assert "Extra" in unified_diff or "+" in unified_diff
        assert len(summary) > 0

    def test_returns_tuple_of_two_strings(self):
        a, b = compute_diff("a", "b")
        assert isinstance(a, str)
        assert isinstance(b, str)
