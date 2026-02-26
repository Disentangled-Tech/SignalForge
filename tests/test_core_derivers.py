"""Tests for core derivers loader and validator (Issue #285, Milestone 2)."""

from __future__ import annotations

import pytest

from app.core_derivers.loader import (
    get_core_passthrough_map,
    get_core_pattern_derivers,
    load_core_derivers,
)
from app.core_derivers.validator import validate_core_derivers
from app.core_taxonomy.loader import get_core_signal_ids


class TestLoadCoreDerivers:
    """Tests for load_core_derivers."""

    def test_returns_dict(self) -> None:
        """load_core_derivers returns a non-empty dict."""
        derivers = load_core_derivers()
        assert isinstance(derivers, dict)
        assert derivers

    def test_has_derivers_key(self) -> None:
        """Loaded derivers has a 'derivers' key."""
        derivers = load_core_derivers()
        assert "derivers" in derivers

    def test_has_passthrough(self) -> None:
        """Derivers 'derivers' section has a non-empty passthrough list."""
        derivers = load_core_derivers()
        inner = derivers["derivers"]
        passthrough = inner.get("passthrough")
        assert isinstance(passthrough, list)
        assert len(passthrough) > 0

    def test_passthrough_entries_are_dicts_with_event_type_signal_id(self) -> None:
        """Each passthrough entry has event_type and signal_id keys."""
        derivers = load_core_derivers()
        for entry in derivers["derivers"]["passthrough"]:
            assert "event_type" in entry, f"Missing event_type in {entry}"
            assert "signal_id" in entry, f"Missing signal_id in {entry}"

    def test_cached_same_object(self) -> None:
        """Repeated calls return the same cached object (lru_cache)."""
        a = load_core_derivers()
        b = load_core_derivers()
        assert a is b

    def test_passthrough_signal_ids_are_in_core_taxonomy(self) -> None:
        """All signal_ids in passthrough entries are in core taxonomy."""
        derivers = load_core_derivers()
        core_ids = get_core_signal_ids()
        for entry in derivers["derivers"]["passthrough"]:
            sid = entry["signal_id"]
            assert sid in core_ids, f"signal_id '{sid}' not in core taxonomy"


class TestGetCorePassthroughMap:
    """Tests for get_core_passthrough_map."""

    def test_returns_dict(self) -> None:
        """get_core_passthrough_map returns a dict."""
        result = get_core_passthrough_map()
        assert isinstance(result, dict)

    def test_non_empty(self) -> None:
        """Passthrough map is non-empty."""
        assert len(get_core_passthrough_map()) > 0

    def test_contains_expected_mappings(self) -> None:
        """Map contains expected canonical event_type -> signal_id entries."""
        m = get_core_passthrough_map()
        assert m.get("funding_raised") == "funding_raised"
        assert m.get("cto_role_posted") == "cto_role_posted"
        assert m.get("repo_activity") == "repo_activity"
        assert m.get("job_posted_engineering") == "job_posted_engineering"

    def test_all_signal_ids_in_core_taxonomy(self) -> None:
        """All values in the passthrough map are valid core signal_ids."""
        core_ids = get_core_signal_ids()
        for event_type, signal_id in get_core_passthrough_map().items():
            assert signal_id in core_ids, (
                f"signal_id '{signal_id}' for event_type '{event_type}' not in core taxonomy"
            )

    def test_cached_same_object(self) -> None:
        """Repeated calls return the same cached dict (lru_cache)."""
        a = get_core_passthrough_map()
        b = get_core_passthrough_map()
        assert a is b

    def test_identity_mapping_for_all_core_passthrough(self) -> None:
        """Each event_type in the core passthrough maps to itself (identity mapping)."""
        for event_type, signal_id in get_core_passthrough_map().items():
            assert event_type == signal_id, (
                f"Expected identity mapping, got {event_type!r} -> {signal_id!r}"
            )


class TestGetCorePatternDerivers:
    """Tests for get_core_pattern_derivers."""

    def test_returns_tuple(self) -> None:
        """get_core_pattern_derivers returns a tuple (hashable for lru_cache)."""
        result = get_core_pattern_derivers()
        assert isinstance(result, tuple)

    def test_each_entry_has_required_keys(self) -> None:
        """Each pattern entry has signal_id, compiled, source_fields, min_confidence."""
        for entry in get_core_pattern_derivers():
            assert "signal_id" in entry
            assert "compiled" in entry
            assert "source_fields" in entry
            assert "min_confidence" in entry

    def test_compiled_patterns_are_regex_objects(self) -> None:
        """Compiled patterns are valid compiled regex objects."""
        import re

        for entry in get_core_pattern_derivers():
            assert hasattr(entry["compiled"], "search"), (
                f"Entry for {entry['signal_id']} must have a compiled regex"
            )
            assert isinstance(entry["compiled"], type(re.compile("")))

    def test_cached_same_object(self) -> None:
        """Repeated calls return the same cached tuple (lru_cache)."""
        a = get_core_pattern_derivers()
        b = get_core_pattern_derivers()
        assert a is b


class TestGetCorePassthroughMapEdgeCases:
    """Edge cases for get_core_passthrough_map (coverage for loader.py non-list path)."""

    def test_passthrough_map_when_derivers_has_inner_list_returns_empty(self) -> None:
        """When 'passthrough' value is not a list, returns empty dict."""
        from unittest.mock import patch

        from app.core_derivers.loader import get_core_passthrough_map

        with patch(
            "app.core_derivers.loader.load_core_derivers",
            return_value={"derivers": {"passthrough": "not_a_list"}},
        ):
            get_core_passthrough_map.cache_clear()
            result = get_core_passthrough_map()
        assert result == {}
        get_core_passthrough_map.cache_clear()


class TestGetCorePatternDeriversWithPatterns:
    """Coverage tests for get_core_pattern_derivers processing paths (lines 76-111)."""

    def _mock_load_with_patterns(self, patterns):
        return {"derivers": {"passthrough": [], "pattern": patterns}}

    def test_pattern_derivers_with_valid_pattern(self) -> None:
        """Pattern entry with valid regex produces compiled deriver."""
        from unittest.mock import patch

        from app.core_derivers.loader import get_core_pattern_derivers

        patterns = [
            {
                "signal_id": "compliance_mentioned",
                "pattern": r"(?i)compliance",
                "source_fields": ["title", "summary"],
                "min_confidence": 0.6,
            }
        ]
        with patch(
            "app.core_derivers.loader.load_core_derivers",
            return_value={"derivers": {"passthrough": [], "pattern": patterns}},
        ):
            get_core_pattern_derivers.cache_clear()
            result = get_core_pattern_derivers()

        assert len(result) == 1
        assert result[0]["signal_id"] == "compliance_mentioned"
        assert result[0]["compiled"].search("SOC2 compliance achieved")
        assert result[0]["source_fields"] == ["title", "summary"]
        assert result[0]["min_confidence"] == 0.6
        get_core_pattern_derivers.cache_clear()

    def test_pattern_derivers_with_default_source_fields_when_none(self) -> None:
        """Pattern entry without source_fields uses default (title, summary)."""
        from unittest.mock import patch

        from app.core_derivers.loader import get_core_pattern_derivers

        patterns = [{"signal_id": "compliance_mentioned", "pattern": r"compliance"}]
        with patch(
            "app.core_derivers.loader.load_core_derivers",
            return_value={"derivers": {"passthrough": [], "pattern": patterns}},
        ):
            get_core_pattern_derivers.cache_clear()
            result = get_core_pattern_derivers()

        assert result[0]["source_fields"] == ["title", "summary"]
        assert result[0]["min_confidence"] is None
        get_core_pattern_derivers.cache_clear()

    def test_pattern_derivers_skips_invalid_regex(self) -> None:
        """Pattern entry with invalid regex is skipped with a warning."""
        from unittest.mock import patch

        from app.core_derivers.loader import get_core_pattern_derivers

        patterns = [
            {"signal_id": "compliance_mentioned", "pattern": r"[invalid"},
        ]
        with (
            patch(
                "app.core_derivers.loader.load_core_derivers",
                return_value={"derivers": {"passthrough": [], "pattern": patterns}},
            ),
        ):
            get_core_pattern_derivers.cache_clear()
            result = get_core_pattern_derivers()

        assert result == ()
        get_core_pattern_derivers.cache_clear()

    def test_pattern_derivers_skips_non_dict_entries(self) -> None:
        """Non-dict pattern entries are skipped."""
        from unittest.mock import patch

        from app.core_derivers.loader import get_core_pattern_derivers

        patterns = ["not_a_dict", 123, None]
        with patch(
            "app.core_derivers.loader.load_core_derivers",
            return_value={"derivers": {"passthrough": [], "pattern": patterns}},
        ):
            get_core_pattern_derivers.cache_clear()
            result = get_core_pattern_derivers()

        assert result == ()
        get_core_pattern_derivers.cache_clear()

    def test_pattern_derivers_fallback_when_source_fields_not_list(self) -> None:
        """Non-list source_fields falls back to default fields."""
        from unittest.mock import patch

        from app.core_derivers.loader import get_core_pattern_derivers

        patterns = [
            {
                "signal_id": "compliance_mentioned",
                "pattern": r"compliance",
                "source_fields": "title",
            }
        ]
        with patch(
            "app.core_derivers.loader.load_core_derivers",
            return_value={"derivers": {"passthrough": [], "pattern": patterns}},
        ):
            get_core_pattern_derivers.cache_clear()
            result = get_core_pattern_derivers()

        assert result[0]["source_fields"] == ["title", "summary"]
        get_core_pattern_derivers.cache_clear()

    def test_pattern_derivers_fallback_when_invalid_source_fields(self) -> None:
        """Source fields with only invalid names fall back to default fields."""
        from unittest.mock import patch

        from app.core_derivers.loader import get_core_pattern_derivers

        patterns = [
            {
                "signal_id": "compliance_mentioned",
                "pattern": r"compliance",
                "source_fields": ["invalid_field", "also_invalid"],
            }
        ]
        with patch(
            "app.core_derivers.loader.load_core_derivers",
            return_value={"derivers": {"passthrough": [], "pattern": patterns}},
        ):
            get_core_pattern_derivers.cache_clear()
            result = get_core_pattern_derivers()

        assert result[0]["source_fields"] == ["title", "summary"]
        get_core_pattern_derivers.cache_clear()

    def test_pattern_derivers_skips_entry_missing_signal_id_or_pattern(self) -> None:
        """Entries missing signal_id or pattern are skipped."""
        from unittest.mock import patch

        from app.core_derivers.loader import get_core_pattern_derivers

        patterns = [
            {"pattern": r"compliance"},
            {"signal_id": "compliance_mentioned"},
        ]
        with patch(
            "app.core_derivers.loader.load_core_derivers",
            return_value={"derivers": {"passthrough": [], "pattern": patterns}},
        ):
            get_core_pattern_derivers.cache_clear()
            result = get_core_pattern_derivers()

        assert result == ()
        get_core_pattern_derivers.cache_clear()

    def test_pattern_derivers_non_list_pattern_returns_empty(self) -> None:
        """When pattern list is not a list, returns empty tuple."""
        from unittest.mock import patch

        from app.core_derivers.loader import get_core_pattern_derivers

        with patch(
            "app.core_derivers.loader.load_core_derivers",
            return_value={"derivers": {"passthrough": [], "pattern": "not_a_list"}},
        ):
            get_core_pattern_derivers.cache_clear()
            result = get_core_pattern_derivers()

        assert result == ()
        get_core_pattern_derivers.cache_clear()


class TestValidateCoreDerivers:
    """Tests for validate_core_derivers."""

    def test_valid_derivers_passes(self) -> None:
        """Well-formed derivers dict passes validation without error."""
        core_ids = frozenset(["funding_raised", "cto_role_posted"])
        derivers = {
            "derivers": {
                "passthrough": [
                    {"event_type": "funding_raised", "signal_id": "funding_raised"},
                    {"event_type": "cto_role_posted", "signal_id": "cto_role_posted"},
                ]
            }
        }
        validate_core_derivers(derivers, core_ids)

    def test_raises_when_not_dict(self) -> None:
        """Non-dict input raises ValueError."""
        with pytest.raises(ValueError, match="must be a dict"):
            validate_core_derivers([], frozenset())  # type: ignore[arg-type]

    def test_raises_when_passthrough_not_list(self) -> None:
        """Non-list passthrough raises ValueError."""
        with pytest.raises(ValueError, match="passthrough"):
            validate_core_derivers(
                {"derivers": {"passthrough": "funding_raised"}},
                frozenset(["funding_raised"]),
            )

    def test_raises_when_passthrough_entry_not_dict(self) -> None:
        """Non-dict passthrough entry raises ValueError."""
        with pytest.raises(ValueError, match="must be a dict"):
            validate_core_derivers(
                {"derivers": {"passthrough": ["not_a_dict"]}},
                frozenset(["funding_raised"]),
            )

    def test_raises_when_pattern_not_list(self) -> None:
        """Non-list pattern field raises ValueError."""
        with pytest.raises(ValueError, match="'pattern' must be a list"):
            validate_core_derivers(
                {"derivers": {"passthrough": [], "pattern": "not_a_list"}},
                frozenset(["funding_raised"]),
            )

    def test_raises_when_passthrough_entry_missing_event_type(self) -> None:
        """Missing event_type in passthrough entry raises ValueError."""
        with pytest.raises(ValueError, match="event_type"):
            validate_core_derivers(
                {"derivers": {"passthrough": [{"signal_id": "funding_raised"}]}},
                frozenset(["funding_raised"]),
            )

    def test_raises_when_passthrough_entry_missing_signal_id(self) -> None:
        """Missing signal_id in passthrough entry raises ValueError."""
        with pytest.raises(ValueError, match="signal_id"):
            validate_core_derivers(
                {"derivers": {"passthrough": [{"event_type": "funding_raised"}]}},
                frozenset(["funding_raised"]),
            )

    def test_raises_when_signal_id_not_in_core_taxonomy(self) -> None:
        """Signal_id not in core taxonomy raises ValueError."""
        with pytest.raises(ValueError, match="unknown signal_id"):
            validate_core_derivers(
                {
                    "derivers": {
                        "passthrough": [
                            {"event_type": "some_event", "signal_id": "not_in_core"}
                        ]
                    }
                },
                frozenset(["funding_raised"]),
            )

    def test_loaded_derivers_pass_validation(self) -> None:
        """The bundled core derivers.yaml passes validation against core taxonomy."""
        derivers = load_core_derivers()
        core_ids = get_core_signal_ids()
        validate_core_derivers(derivers, core_ids)

    def test_empty_passthrough_passes(self) -> None:
        """Empty passthrough list is valid."""
        validate_core_derivers({"derivers": {"passthrough": []}}, frozenset())

    def test_parity_with_fractional_cto_passthrough_count(self) -> None:
        """Core passthrough count matches fractional_cto_v1 passthrough count (no drift)."""
        import os

        import yaml

        pack_derivers_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "packs",
            "fractional_cto_v1",
            "derivers.yaml",
        )
        with open(pack_derivers_path) as f:
            pack_derivers = yaml.safe_load(f)

        pack_pt = pack_derivers.get("derivers", {}).get("passthrough", [])
        core_pt = load_core_derivers().get("derivers", {}).get("passthrough", [])
        assert len(core_pt) == len(pack_pt), (
            f"Core passthrough count ({len(core_pt)}) diverged from "
            f"fractional_cto_v1 ({len(pack_pt)})"
        )

    def test_raises_when_inner_derivers_not_dict(self) -> None:
        """When 'derivers' key value is not a dict, raises ValueError."""
        with pytest.raises(ValueError, match="'derivers' key containing a dict"):
            validate_core_derivers({"derivers": "not_a_dict"}, frozenset(["funding_raised"]))

    def test_pattern_validation_called_for_pattern_entries(self) -> None:
        """When pattern entries exist, regex safety validation is applied."""
        from app.packs.schemas import ValidationError

        core_ids = frozenset(["funding_raised"])
        with pytest.raises(ValidationError):
            validate_core_derivers(
                {
                    "derivers": {
                        "passthrough": [],
                        "pattern": [
                            {
                                "signal_id": "funding_raised",
                                "pattern": r"(.+)+",
                            }
                        ],
                    }
                },
                core_ids,
            )

    def test_pattern_validation_unknown_signal_id_raises(self) -> None:
        """Pattern entry with unknown signal_id raises ValueError."""
        with pytest.raises(ValueError, match="unknown signal_id"):
            validate_core_derivers(
                {
                    "derivers": {
                        "passthrough": [],
                        "pattern": [
                            {
                                "signal_id": "unknown_signal",
                                "pattern": r"compliance",
                            }
                        ],
                    }
                },
                frozenset(["funding_raised"]),
            )

    def test_pattern_entry_not_dict_raises(self) -> None:
        """Non-dict pattern entry raises ValueError."""
        with pytest.raises(ValueError, match="Pattern entry 0 must be a dict"):
            validate_core_derivers(
                {
                    "derivers": {
                        "passthrough": [],
                        "pattern": ["not_a_dict"],
                    }
                },
                frozenset(["funding_raised"]),
            )

    def test_pattern_entry_missing_signal_id_raises(self) -> None:
        """Pattern entry without signal_id raises ValueError."""
        with pytest.raises(ValueError, match="signal_id"):
            validate_core_derivers(
                {
                    "derivers": {
                        "passthrough": [],
                        "pattern": [{"pattern": r"compliance"}],
                    }
                },
                frozenset(["funding_raised"]),
            )

    def test_parity_with_fractional_cto_passthrough_entries(self) -> None:
        """Core passthrough entries are a superset of fractional_cto_v1 entries."""
        import os

        import yaml

        pack_derivers_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "packs",
            "fractional_cto_v1",
            "derivers.yaml",
        )
        with open(pack_derivers_path) as f:
            pack_derivers = yaml.safe_load(f)

        pack_map = {
            e["event_type"]: e["signal_id"]
            for e in pack_derivers.get("derivers", {}).get("passthrough", [])
        }
        core_map = get_core_passthrough_map()
        for etype, sid in pack_map.items():
            assert core_map.get(etype) == sid, (
                f"Core passthrough missing or differs for event_type '{etype}': "
                f"expected '{sid}', got '{core_map.get(etype)}'"
            )
