"""Core derivers module tests (Issue #285, Milestone 2).

Covers: load, validate, passthrough/pattern output stability, regex safety,
and signal_id cross-reference with core taxonomy.
"""

from __future__ import annotations

import re

import pytest


class TestLoadCoreDrivers:
    """load_core_derivers() returns valid dict with expected structure."""

    def test_load_returns_dict(self) -> None:
        from app.core_derivers.loader import load_core_derivers

        result = load_core_derivers()
        assert isinstance(result, dict)

    def test_load_has_derivers_key(self) -> None:
        from app.core_derivers.loader import load_core_derivers

        result = load_core_derivers()
        assert "derivers" in result

    def test_load_derivers_has_passthrough(self) -> None:
        from app.core_derivers.loader import load_core_derivers

        result = load_core_derivers()
        inner = result["derivers"]
        assert "passthrough" in inner
        assert isinstance(inner["passthrough"], list)
        assert len(inner["passthrough"]) > 0

    def test_load_is_idempotent(self) -> None:
        from app.core_derivers.loader import load_core_derivers

        first = load_core_derivers()
        second = load_core_derivers()
        assert first == second


class TestGetCorePassthroughMap:
    """get_core_passthrough_map() returns correct event_type -> signal_id mapping."""

    def test_returns_mapping(self) -> None:
        """get_core_passthrough_map returns an immutable Mapping (MappingProxyType).

        The return type is MappingProxyType, not dict, to prevent mutation of the
        shared cached reference (Fix #4). It supports all read operations.
        """
        from collections.abc import Mapping
        from types import MappingProxyType

        from app.core_derivers.loader import get_core_passthrough_map

        result = get_core_passthrough_map()
        assert isinstance(result, Mapping)
        assert isinstance(result, MappingProxyType)

    def test_nonempty(self) -> None:
        from app.core_derivers.loader import get_core_passthrough_map

        result = get_core_passthrough_map()
        assert len(result) > 0

    def test_contains_fractional_cto_mappings(self) -> None:
        """All fractional_cto_v1 passthrough mappings are present in core."""
        from app.core_derivers.loader import get_core_passthrough_map

        expected = {
            "funding_raised": "funding_raised",
            "job_posted_engineering": "job_posted_engineering",
            "job_posted_infra": "job_posted_infra",
            "headcount_growth": "headcount_growth",
            "launch_major": "launch_major",
            "api_launched": "api_launched",
            "ai_feature_launched": "ai_feature_launched",
            "enterprise_feature": "enterprise_feature",
            "compliance_mentioned": "compliance_mentioned",
            "enterprise_customer": "enterprise_customer",
            "regulatory_deadline": "regulatory_deadline",
            "founder_urgency_language": "founder_urgency_language",
            "revenue_milestone": "revenue_milestone",
            "cto_role_posted": "cto_role_posted",
            "no_cto_detected": "no_cto_detected",
            "fractional_request": "fractional_request",
            "advisor_request": "advisor_request",
            "cto_hired": "cto_hired",
            "repo_activity": "repo_activity",
        }
        passthrough = get_core_passthrough_map()
        for event_type, signal_id in expected.items():
            assert event_type in passthrough, f"missing passthrough for '{event_type}'"
            assert passthrough[event_type] == signal_id, (
                f"expected passthrough['{event_type}'] == '{signal_id}', "
                f"got '{passthrough[event_type]}'"
            )

    def test_incorporation_passthrough(self) -> None:
        """incorporation event type maps to incorporation signal_id."""
        from app.core_derivers.loader import get_core_passthrough_map

        passthrough = get_core_passthrough_map()
        assert "incorporation" in passthrough
        assert passthrough["incorporation"] == "incorporation"

    def test_stable_across_calls(self) -> None:
        """get_core_passthrough_map() is cached and returns the same object."""
        from app.core_derivers.loader import get_core_passthrough_map

        first = get_core_passthrough_map()
        second = get_core_passthrough_map()
        assert first is second  # lru_cache returns same object

    def test_all_signal_ids_in_core_taxonomy(self) -> None:
        """Every signal_id in the passthrough map is in the core taxonomy."""
        from app.core_derivers.loader import get_core_passthrough_map
        from app.core_taxonomy.loader import get_core_signal_ids

        passthrough = get_core_passthrough_map()
        core_ids = get_core_signal_ids()
        for event_type, signal_id in passthrough.items():
            assert signal_id in core_ids, (
                f"passthrough signal_id '{signal_id}' (for '{event_type}') not in core taxonomy"
            )


class TestGetCorePatternDerivers:
    """get_core_pattern_derivers() returns tuple of compiled pattern derivers."""

    def test_returns_tuple(self) -> None:
        from app.core_derivers.loader import get_core_pattern_derivers

        result = get_core_pattern_derivers()
        assert isinstance(result, tuple)

    def test_stable_across_calls(self) -> None:
        """get_core_pattern_derivers() is cached and returns the same object."""
        from app.core_derivers.loader import get_core_pattern_derivers

        first = get_core_pattern_derivers()
        second = get_core_pattern_derivers()
        assert first is second  # lru_cache returns same object

    def test_each_entry_has_compiled_regex(self) -> None:
        """Every pattern deriver has a 'compiled' re.Pattern field."""
        from app.core_derivers.loader import get_core_pattern_derivers

        for entry in get_core_pattern_derivers():
            assert "compiled" in entry, f"missing compiled key in {entry}"
            assert isinstance(entry["compiled"], re.Pattern), (
                f"compiled is not a re.Pattern in {entry}"
            )

    def test_each_entry_has_signal_id(self) -> None:
        """Every pattern deriver has a 'signal_id' field."""
        from app.core_derivers.loader import get_core_pattern_derivers

        for entry in get_core_pattern_derivers():
            assert "signal_id" in entry, f"missing signal_id in {entry}"

    def test_compiles_pattern_entries_from_derivers(self) -> None:
        """Pattern entries with 'pattern' key are compiled to re.Pattern.

        Uses mock to inject pattern entries and exercises the loop body in loader.py.
        Cache is cleared before and restored after the test.
        """
        from unittest.mock import patch

        import app.core_derivers.loader as loader_mod

        loader_mod.get_core_pattern_derivers.cache_clear()
        try:
            synthetic = {
                "derivers": {
                    "pattern": [
                        {
                            "pattern": r"\bfunding\b",
                            "signal_id": "funding_raised",
                            "source_fields": ["title"],
                        },
                        "not_a_dict",  # should be skipped
                        {"signal_id": "no_pattern_key"},  # no pattern/regex; should be skipped
                    ]
                }
            }
            with patch.object(loader_mod, "load_core_derivers", return_value=synthetic):
                result = loader_mod.get_core_pattern_derivers()

            assert len(result) == 1
            entry = result[0]
            assert entry["signal_id"] == "funding_raised"
            assert isinstance(entry["compiled"], re.Pattern)
            assert entry["source_fields"] == ["title"]
        finally:
            loader_mod.get_core_pattern_derivers.cache_clear()

    def test_compiles_regex_key_entries(self) -> None:
        """Pattern entries with 'regex' key are compiled to re.Pattern."""
        from unittest.mock import patch

        import app.core_derivers.loader as loader_mod

        loader_mod.get_core_pattern_derivers.cache_clear()
        try:
            synthetic = {
                "derivers": {
                    "pattern": [
                        {
                            "regex": r"\bcto\b",
                            "signal_id": "cto_role_posted",
                        },
                    ]
                }
            }
            with patch.object(loader_mod, "load_core_derivers", return_value=synthetic):
                result = loader_mod.get_core_pattern_derivers()

            assert len(result) == 1
            assert isinstance(result[0]["compiled"], re.Pattern)
            assert result[0]["signal_id"] == "cto_role_posted"
        finally:
            loader_mod.get_core_pattern_derivers.cache_clear()


class TestValidateCoreDrivers:
    """validate_core_derivers() raises CoreDeriversValidationError on invalid input."""

    def _valid_passthrough(self) -> dict:
        return {
            "derivers": {
                "passthrough": [
                    {"event_type": "funding_raised", "signal_id": "funding_raised"},
                ]
            }
        }

    def test_valid_passthrough_passes(self) -> None:
        from app.core_derivers.validator import validate_core_derivers

        validate_core_derivers(self._valid_passthrough())  # must not raise

    def test_non_dict_raises(self) -> None:
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="must be a dict"):
            validate_core_derivers([])  # type: ignore[arg-type]

    def test_missing_derivers_key_raises(self) -> None:
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="'derivers' key"):
            validate_core_derivers({})

    def test_derivers_value_not_dict_raises(self) -> None:
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="must be a dict"):
            validate_core_derivers({"derivers": "bad"})

    def test_passthrough_missing_event_type_raises(self) -> None:
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="event_type"):
            validate_core_derivers({"derivers": {"passthrough": [{"signal_id": "funding_raised"}]}})

    def test_passthrough_missing_signal_id_raises(self) -> None:
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="signal_id"):
            validate_core_derivers(
                {"derivers": {"passthrough": [{"event_type": "funding_raised"}]}}
            )

    def test_passthrough_unknown_signal_id_raises(self) -> None:
        """Passthrough referencing signal_id not in core taxonomy raises."""
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="not in core taxonomy"):
            validate_core_derivers(
                {
                    "derivers": {
                        "passthrough": [
                            {"event_type": "mystery_event", "signal_id": "mystery_signal_xyz"}
                        ]
                    }
                }
            )

    def test_pattern_missing_signal_id_raises(self) -> None:
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="signal_id"):
            validate_core_derivers({"derivers": {"pattern": [{"pattern": r"\bfunding\b"}]}})

    def test_pattern_missing_pattern_or_regex_raises(self) -> None:
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="pattern.*regex|regex.*pattern"):
            validate_core_derivers({"derivers": {"pattern": [{"signal_id": "funding_raised"}]}})

    def test_pattern_unknown_signal_id_raises(self) -> None:
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="not in core taxonomy"):
            validate_core_derivers(
                {
                    "derivers": {
                        "pattern": [{"pattern": r"\bfunding\b", "signal_id": "ghost_signal_xyz"}]
                    }
                }
            )

    def test_pattern_disallowed_source_field_raises(self) -> None:
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="not allowed"):
            validate_core_derivers(
                {
                    "derivers": {
                        "pattern": [
                            {
                                "pattern": r"\bfunding\b",
                                "signal_id": "funding_raised",
                                "source_fields": ["raw"],  # not in ALLOWED_PATTERN_SOURCE_FIELDS
                            }
                        ]
                    }
                }
            )

    def test_pattern_allowed_source_fields_pass(self) -> None:
        from app.core_derivers.validator import validate_core_derivers

        validate_core_derivers(
            {
                "derivers": {
                    "pattern": [
                        {
                            "pattern": r"\bfunding\b",
                            "signal_id": "funding_raised",
                            "source_fields": ["title", "summary"],
                        }
                    ]
                }
            }
        )  # must not raise

    def test_dangerous_regex_raises(self) -> None:
        """Catastrophic backtracking patterns are rejected."""
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="backtracking|unsafe|catastrophic"):
            validate_core_derivers(
                {"derivers": {"pattern": [{"pattern": r"(.*)+", "signal_id": "funding_raised"}]}}
            )

    def test_invalid_regex_syntax_raises(self) -> None:
        from app.core_derivers.validator import (
            CoreDeriversValidationError,
            validate_core_derivers,
        )

        with pytest.raises(CoreDeriversValidationError, match="invalid|syntax|regex"):
            validate_core_derivers(
                {
                    "derivers": {
                        "pattern": [{"pattern": r"(unclosed", "signal_id": "funding_raised"}]
                    }
                }
            )

    def test_passthrough_only_valid_no_pattern_key(self) -> None:
        """Derivers with only passthrough (no pattern key) are valid."""
        from app.core_derivers.validator import validate_core_derivers

        validate_core_derivers(
            {
                "derivers": {
                    "passthrough": [
                        {"event_type": "funding_raised", "signal_id": "funding_raised"},
                        {"event_type": "cto_hired", "signal_id": "cto_hired"},
                    ]
                }
            }
        )  # must not raise

    def test_empty_passthrough_list_is_valid(self) -> None:
        from app.core_derivers.validator import validate_core_derivers

        validate_core_derivers({"derivers": {"passthrough": []}})  # must not raise


class TestLoaderYamlErrorHandling:
    """Fix #3: yaml.YAMLError is converted to ValueError so deriver engine fallback fires."""

    def test_malformed_yaml_raises_value_error(self) -> None:
        """When derivers.yaml is malformed YAML, load_core_derivers raises ValueError."""
        from unittest.mock import MagicMock, patch

        import yaml as _yaml

        import app.core_derivers.loader as loader_mod

        bad_yaml = MagicMock(side_effect=_yaml.YAMLError("bad yaml"))
        with patch.object(_yaml, "safe_load", bad_yaml):
            with pytest.raises(ValueError, match="malformed"):
                loader_mod.load_core_derivers()

    def test_validation_error_is_value_error_subclass(self) -> None:
        """CoreDeriversValidationError is a ValueError subclass (caught by engine fallback)."""
        from app.core_derivers.validator import CoreDeriversValidationError

        assert issubclass(CoreDeriversValidationError, ValueError)

    def test_validation_error_caught_as_value_error(self) -> None:
        """validate_core_derivers raises an exception catchable as ValueError."""
        from app.core_derivers.validator import validate_core_derivers

        with pytest.raises(ValueError):
            validate_core_derivers({})  # missing 'derivers' key


class TestCoreDerivesFileIntegrity:
    """Integration: the real derivers.yaml loads and validates without errors."""

    def test_file_loads_and_validates(self) -> None:
        from app.core_derivers.loader import load_core_derivers

        result = load_core_derivers()
        assert "derivers" in result

    def test_all_passthrough_signal_ids_in_taxonomy(self) -> None:
        """Every passthrough signal_id in derivers.yaml is in core taxonomy signal_ids."""
        from app.core_derivers.loader import load_core_derivers
        from app.core_taxonomy.loader import get_core_signal_ids

        data = load_core_derivers()
        core_ids = get_core_signal_ids()
        passthrough = data.get("derivers", {}).get("passthrough") or []
        for entry in passthrough:
            sid = entry.get("signal_id")
            assert sid in core_ids, (
                f"derivers.yaml passthrough references '{sid}' not in core taxonomy"
            )

    def test_no_duplicate_event_types(self) -> None:
        """Each event_type appears at most once in the passthrough list."""
        from app.core_derivers.loader import load_core_derivers

        data = load_core_derivers()
        passthrough = data.get("derivers", {}).get("passthrough") or []
        event_types = [e.get("event_type") for e in passthrough if isinstance(e, dict)]
        assert len(event_types) == len(set(event_types)), (
            "derivers.yaml passthrough contains duplicate event_types"
        )
