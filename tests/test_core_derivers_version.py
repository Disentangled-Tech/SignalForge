"""Core derivers version tests (Evidence Bundle Store M1, Issue #276).

Unit tests for get_core_derivers_version(): presence, stability, and
behavior when optional version is present in YAML vs content hash fallback.
"""

from __future__ import annotations

import re


class TestGetCoreDeriversVersion:
    """get_core_derivers_version() returns a stable, non-empty string."""

    def test_returns_non_empty_string(self) -> None:
        from app.core_derivers.loader import get_core_derivers_version

        result = get_core_derivers_version()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_stable_across_calls(self) -> None:
        """Version is cached and returns the same value on multiple calls."""
        from app.core_derivers.loader import get_core_derivers_version

        first = get_core_derivers_version()
        second = get_core_derivers_version()
        assert first == second
        assert first is second or first == second  # cached or equal

    def test_either_yaml_version_or_64_char_hex(self) -> None:
        """With real derivers.yaml: version is either YAML version or SHA-256 hex (64 chars)."""
        from app.core_derivers.loader import get_core_derivers_version

        result = get_core_derivers_version()
        if re.fullmatch(r"[a-f0-9]{64}", result):
            assert len(result) == 64
        else:
            assert result.strip() != ""

    def test_when_version_in_yaml_returns_it(self) -> None:
        """When derivers has top-level 'version' key, that value is returned."""
        from unittest.mock import patch

        import app.core_derivers.loader as loader_mod

        loader_mod.get_core_derivers_version.cache_clear()
        try:
            synthetic = {
                "version": "test-derivers-1.0",
                "derivers": {
                    "passthrough": [
                        {"event_type": "funding_raised", "signal_id": "funding_raised"},
                    ],
                },
            }
            with patch.object(loader_mod, "load_core_derivers", return_value=synthetic):
                result = loader_mod.get_core_derivers_version()
            assert result == "test-derivers-1.0"
        finally:
            loader_mod.get_core_derivers_version.cache_clear()

    def test_when_version_absent_returns_content_hash(self) -> None:
        """When derivers has no version key, returns SHA-256 hex of file content."""
        from unittest.mock import patch

        import app.core_derivers.loader as loader_mod

        loader_mod.get_core_derivers_version.cache_clear()
        try:
            synthetic = {
                "derivers": {
                    "passthrough": [
                        {"event_type": "funding_raised", "signal_id": "funding_raised"},
                    ],
                },
            }
            with patch.object(loader_mod, "load_core_derivers", return_value=synthetic):
                result = loader_mod.get_core_derivers_version()
            assert isinstance(result, str)
            assert len(result) == 64
            assert re.fullmatch(r"[a-f0-9]{64}", result), "expected 64-char hex digest"
        finally:
            loader_mod.get_core_derivers_version.cache_clear()
