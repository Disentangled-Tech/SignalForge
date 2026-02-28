"""Core taxonomy module tests (Issue #285, Milestone 1).

Covers: load, validate, is_valid_signal_id, superset assertions vs pack taxonomy
and SIGNAL_EVENT_TYPES.
"""

from __future__ import annotations

import pytest


class TestLoadCoreTaxonomy:
    """load_core_taxonomy() returns valid, non-empty dict."""

    def test_load_returns_dict(self) -> None:
        from app.core_taxonomy.loader import load_core_taxonomy

        result = load_core_taxonomy()
        assert isinstance(result, dict)

    def test_load_has_signal_ids(self) -> None:
        from app.core_taxonomy.loader import load_core_taxonomy

        result = load_core_taxonomy()
        assert "signal_ids" in result
        assert isinstance(result["signal_ids"], list)
        assert len(result["signal_ids"]) > 0

    def test_load_has_dimensions(self) -> None:
        from app.core_taxonomy.loader import load_core_taxonomy

        result = load_core_taxonomy()
        assert "dimensions" in result
        dims = result["dimensions"]
        assert isinstance(dims, dict)
        assert len(dims) > 0

    def test_load_dimension_keys(self) -> None:
        """Dimensions M, C, P, G are all present."""
        from app.core_taxonomy.loader import load_core_taxonomy

        result = load_core_taxonomy()
        dims = result["dimensions"]
        for key in ("M", "C", "P", "G"):
            assert key in dims, f"dimension '{key}' missing"

    def test_load_is_idempotent(self) -> None:
        """Calling load_core_taxonomy twice returns equivalent results."""
        from app.core_taxonomy.loader import load_core_taxonomy

        first = load_core_taxonomy()
        second = load_core_taxonomy()
        assert first["signal_ids"] == second["signal_ids"]


class TestGetCoreSignalIds:
    """get_core_signal_ids() returns a frozenset of all canonical signal_ids."""

    def test_returns_frozenset(self) -> None:
        from app.core_taxonomy.loader import get_core_signal_ids

        result = get_core_signal_ids()
        assert isinstance(result, frozenset)

    def test_nonempty(self) -> None:
        from app.core_taxonomy.loader import get_core_signal_ids

        result = get_core_signal_ids()
        assert len(result) > 0

    def test_contains_fractional_cto_ids(self) -> None:
        """Core taxonomy is a superset of fractional_cto_v1 signal_ids."""
        from app.core_taxonomy.loader import get_core_signal_ids

        fractional_cto_ids = {
            "funding_raised",
            "job_posted_engineering",
            "job_posted_infra",
            "headcount_growth",
            "launch_major",
            "api_launched",
            "ai_feature_launched",
            "enterprise_feature",
            "compliance_mentioned",
            "enterprise_customer",
            "regulatory_deadline",
            "founder_urgency_language",
            "revenue_milestone",
            "cto_role_posted",
            "no_cto_detected",
            "fractional_request",
            "advisor_request",
            "cto_hired",
            "repo_activity",
        }
        core_ids = get_core_signal_ids()
        missing = fractional_cto_ids - core_ids
        assert not missing, f"core taxonomy missing fractional_cto_v1 ids: {sorted(missing)}"

    def test_contains_event_types_signal_event_types(self) -> None:
        """Core taxonomy is a superset of ingestion event_types.SIGNAL_EVENT_TYPES."""
        from app.core_taxonomy.loader import get_core_signal_ids
        from app.ingestion.event_types import SIGNAL_EVENT_TYPES

        core_ids = get_core_signal_ids()
        missing = SIGNAL_EVENT_TYPES - core_ids
        assert not missing, (
            f"core taxonomy must be superset of SIGNAL_EVENT_TYPES, missing: {sorted(missing)}"
        )

    def test_contains_repo_activity(self) -> None:
        from app.core_taxonomy.loader import get_core_signal_ids

        assert "repo_activity" in get_core_signal_ids()

    def test_contains_incorporation(self) -> None:
        from app.core_taxonomy.loader import get_core_signal_ids

        assert "incorporation" in get_core_signal_ids()

    def test_stable_across_calls(self) -> None:
        """get_core_signal_ids() is cached and returns the same object."""
        from app.core_taxonomy.loader import get_core_signal_ids

        first = get_core_signal_ids()
        second = get_core_signal_ids()
        assert first is second  # lru_cache returns same object


class TestIsValidSignalId:
    """is_valid_signal_id() returns True for known ids, False otherwise."""

    def test_known_id_returns_true(self) -> None:
        from app.core_taxonomy.loader import is_valid_signal_id

        assert is_valid_signal_id("funding_raised") is True

    def test_unknown_id_returns_false(self) -> None:
        from app.core_taxonomy.loader import is_valid_signal_id

        assert is_valid_signal_id("totally_unknown_signal_xyz") is False

    def test_empty_string_returns_false(self) -> None:
        from app.core_taxonomy.loader import is_valid_signal_id

        assert is_valid_signal_id("") is False

    def test_all_fractional_cto_ids_valid(self) -> None:
        from app.core_taxonomy.loader import is_valid_signal_id

        for sid in (
            "funding_raised",
            "job_posted_engineering",
            "job_posted_infra",
            "headcount_growth",
            "launch_major",
            "api_launched",
            "ai_feature_launched",
            "enterprise_feature",
            "compliance_mentioned",
            "enterprise_customer",
            "regulatory_deadline",
            "founder_urgency_language",
            "revenue_milestone",
            "cto_role_posted",
            "no_cto_detected",
            "fractional_request",
            "advisor_request",
            "cto_hired",
            "repo_activity",
        ):
            assert is_valid_signal_id(sid) is True, f"expected '{sid}' to be valid"

    def test_incorporation_valid(self) -> None:
        from app.core_taxonomy.loader import is_valid_signal_id

        assert is_valid_signal_id("incorporation") is True


class TestValidateCoreTaxonomy:
    """validate_core_taxonomy() raises CoreTaxonomyValidationError on invalid input."""

    def test_valid_taxonomy_passes(self) -> None:
        from app.core_taxonomy.validator import validate_core_taxonomy

        valid = {"signal_ids": ["foo", "bar"], "dimensions": {"M": ["foo"]}}
        validate_core_taxonomy(valid)  # must not raise

    def test_non_dict_raises(self) -> None:
        from app.core_taxonomy.validator import (
            CoreTaxonomyValidationError,
            validate_core_taxonomy,
        )

        with pytest.raises(CoreTaxonomyValidationError, match="must be a dict"):
            validate_core_taxonomy([])  # type: ignore[arg-type]

    def test_missing_signal_ids_raises(self) -> None:
        from app.core_taxonomy.validator import (
            CoreTaxonomyValidationError,
            validate_core_taxonomy,
        )

        with pytest.raises(CoreTaxonomyValidationError, match="signal_ids"):
            validate_core_taxonomy({})

    def test_empty_signal_ids_raises(self) -> None:
        from app.core_taxonomy.validator import (
            CoreTaxonomyValidationError,
            validate_core_taxonomy,
        )

        with pytest.raises(CoreTaxonomyValidationError, match="not be empty"):
            validate_core_taxonomy({"signal_ids": []})

    def test_duplicate_signal_id_raises(self) -> None:
        from app.core_taxonomy.validator import (
            CoreTaxonomyValidationError,
            validate_core_taxonomy,
        )

        with pytest.raises(CoreTaxonomyValidationError, match="duplicate"):
            validate_core_taxonomy({"signal_ids": ["foo", "foo"]})

    def test_dimension_references_missing_signal_id_raises(self) -> None:
        from app.core_taxonomy.validator import (
            CoreTaxonomyValidationError,
            validate_core_taxonomy,
        )

        with pytest.raises(CoreTaxonomyValidationError, match="not in signal_ids"):
            validate_core_taxonomy(
                {
                    "signal_ids": ["foo"],
                    "dimensions": {"M": ["bar"]},  # bar not in signal_ids
                }
            )

    def test_dimensions_not_dict_raises(self) -> None:
        from app.core_taxonomy.validator import (
            CoreTaxonomyValidationError,
            validate_core_taxonomy,
        )

        with pytest.raises(CoreTaxonomyValidationError, match="dimensions.*dict"):
            validate_core_taxonomy({"signal_ids": ["foo"], "dimensions": ["bad"]})  # type: ignore[arg-type]

    def test_dimension_entry_not_list_raises(self) -> None:
        from app.core_taxonomy.validator import (
            CoreTaxonomyValidationError,
            validate_core_taxonomy,
        )

        with pytest.raises(CoreTaxonomyValidationError, match="must be a list"):
            validate_core_taxonomy(
                {
                    "signal_ids": ["foo"],
                    "dimensions": {"M": "foo"},  # type: ignore[dict-item]
                }
            )

    def test_non_string_signal_id_raises(self) -> None:
        from app.core_taxonomy.validator import (
            CoreTaxonomyValidationError,
            validate_core_taxonomy,
        )

        with pytest.raises(CoreTaxonomyValidationError, match="non-empty strings"):
            validate_core_taxonomy({"signal_ids": [123]})  # type: ignore[list-item]

    def test_none_signal_id_raises(self) -> None:
        from app.core_taxonomy.validator import (
            CoreTaxonomyValidationError,
            validate_core_taxonomy,
        )

        with pytest.raises(CoreTaxonomyValidationError, match="non-empty strings"):
            validate_core_taxonomy({"signal_ids": [None]})  # type: ignore[list-item]

    def test_dimensions_absent_passes(self) -> None:
        """Taxonomy without dimensions key is valid."""
        from app.core_taxonomy.validator import validate_core_taxonomy

        validate_core_taxonomy({"signal_ids": ["foo"]})  # must not raise


class TestCoreTaxonomyIntegrity:
    """Structural integrity of the actual taxonomy.yaml file."""

    def test_all_dimension_ids_in_signal_ids(self) -> None:
        """Every signal_id referenced in a dimension is in the top-level signal_ids list."""
        from app.core_taxonomy.loader import load_core_taxonomy

        data = load_core_taxonomy()
        signal_id_set = set(data["signal_ids"])
        for dim_key, dim_ids in data.get("dimensions", {}).items():
            for sid in dim_ids:
                assert sid in signal_id_set, (
                    f"dimension '{dim_key}' references '{sid}' not in signal_ids"
                )

    def test_signal_ids_are_unique(self) -> None:
        from app.core_taxonomy.loader import load_core_taxonomy

        data = load_core_taxonomy()
        ids = data["signal_ids"]
        assert len(ids) == len(set(ids)), "taxonomy.yaml contains duplicate signal_ids"
