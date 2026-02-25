"""Tests for SignalScorer band resolution (Issue #242, Phase 2)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.signal_scorer import resolve_band


def _make_pack_with_bands(ignore_max: int, watch_max: int, high_priority_min: int) -> MagicMock:
    """Build mock pack with recommendation_bands."""
    pack = MagicMock()
    pack.scoring = {
        "recommendation_bands": {
            "ignore_max": ignore_max,
            "watch_max": watch_max,
            "high_priority_min": high_priority_min,
        }
    }
    return pack


class TestResolveBand:
    """resolve_band(composite, pack) returns correct band."""

    def test_none_when_pack_none(self) -> None:
        """pack=None returns None."""
        assert resolve_band(50, None) is None

    def test_none_when_pack_has_no_bands(self) -> None:
        """Pack without recommendation_bands returns None."""
        pack = MagicMock()
        pack.scoring = {}
        assert resolve_band(50, pack) is None

    def test_none_when_bands_invalid(self) -> None:
        """Pack with invalid bands (missing keys) returns None."""
        pack = MagicMock()
        pack.scoring = {"recommendation_bands": {"ignore_max": 34}}
        assert resolve_band(50, pack) is None

    def test_fractional_cto_boundaries_ignore(self) -> None:
        """Composite <= 34 -> IGNORE (fractional_cto_v1 bands)."""
        pack = _make_pack_with_bands(34, 69, 70)
        assert resolve_band(0, pack) == "IGNORE"
        assert resolve_band(34, pack) == "IGNORE"

    def test_fractional_cto_boundaries_watch(self) -> None:
        """35 <= composite <= 69 -> WATCH (fractional_cto_v1 bands)."""
        pack = _make_pack_with_bands(34, 69, 70)
        assert resolve_band(35, pack) == "WATCH"
        assert resolve_band(50, pack) == "WATCH"
        assert resolve_band(69, pack) == "WATCH"

    def test_fractional_cto_boundaries_high_priority(self) -> None:
        """Composite >= 70 -> HIGH_PRIORITY (fractional_cto_v1 bands)."""
        pack = _make_pack_with_bands(34, 69, 70)
        assert resolve_band(70, pack) == "HIGH_PRIORITY"
        assert resolve_band(100, pack) == "HIGH_PRIORITY"
