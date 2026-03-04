"""Tests for suppressed_signal_phrases module (Issue #120 M2)."""

from __future__ import annotations

from app.services.ore.suppressed_signal_phrases import get_phrases_for_suppressed_signals


def test_empty_signal_ids_returns_empty_dict() -> None:
    """Empty signal_ids returns empty dict."""
    assert get_phrases_for_suppressed_signals(set()) == {}


def test_known_signal_id_returns_phrases() -> None:
    """Known signal_id (e.g. financial_distress) returns non-empty phrase list."""
    result = get_phrases_for_suppressed_signals({"financial_distress"})
    assert "financial_distress" in result
    assert isinstance(result["financial_distress"], list)
    assert len(result["financial_distress"]) > 0
    assert "financial trouble" in result["financial_distress"]
    assert "struggling financially" in result["financial_distress"]


def test_unknown_signal_id_omitted() -> None:
    """Unknown signal_id is omitted from result (no phrase list)."""
    result = get_phrases_for_suppressed_signals({"unknown_signal_xyz"})
    assert result == {}


def test_mixed_known_and_unknown_returns_only_known() -> None:
    """Mix of known and unknown returns only known signal_ids."""
    result = get_phrases_for_suppressed_signals(
        {"financial_distress", "unknown_xyz", "distress_mentioned"}
    )
    assert "unknown_xyz" not in result
    assert "financial_distress" in result
    assert "distress_mentioned" in result
    assert len(result["distress_mentioned"]) > 0
