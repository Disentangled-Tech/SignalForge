"""Tests for core taxonomy loader and validator (Issue #285, Milestone 1)."""

from __future__ import annotations

import pytest

from app.core_taxonomy.loader import (
    get_core_signal_ids,
    is_valid_signal_id,
    load_core_taxonomy,
)
from app.core_taxonomy.validator import validate_core_taxonomy


class TestLoadCoreTaxonomy:
    """Tests for load_core_taxonomy."""

    def test_returns_dict(self) -> None:
        """load_core_taxonomy returns a non-empty dict."""
        taxonomy = load_core_taxonomy()
        assert isinstance(taxonomy, dict)
        assert taxonomy

    def test_has_signal_ids(self) -> None:
        """Loaded taxonomy has a non-empty signal_ids list."""
        taxonomy = load_core_taxonomy()
        signal_ids = taxonomy.get("signal_ids")
        assert isinstance(signal_ids, list)
        assert len(signal_ids) > 0

    def test_has_expected_signal_ids(self) -> None:
        """Core taxonomy contains the full set of expected signal identifiers."""
        expected = {
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
        taxonomy = load_core_taxonomy()
        actual = set(taxonomy["signal_ids"])
        assert expected <= actual, f"Missing signal_ids: {expected - actual}"

    def test_has_dimensions(self) -> None:
        """Loaded taxonomy has a dimensions dict."""
        taxonomy = load_core_taxonomy()
        dimensions = taxonomy.get("dimensions")
        assert isinstance(dimensions, dict)
        assert dimensions

    def test_dimensions_cover_momentum_complexity_pressure_leadership_gap(self) -> None:
        """Core taxonomy defines M, C, P, G dimension keys."""
        taxonomy = load_core_taxonomy()
        dims = taxonomy["dimensions"]
        assert "M" in dims
        assert "C" in dims
        assert "P" in dims
        assert "G" in dims

    def test_all_dimension_entries_are_valid_signal_ids(self) -> None:
        """Every signal_id referenced in dimensions exists in signal_ids."""
        taxonomy = load_core_taxonomy()
        signal_id_set = set(taxonomy["signal_ids"])
        for dim_key, sids in taxonomy["dimensions"].items():
            for sid in sids:
                assert sid in signal_id_set, (
                    f"Dimension '{dim_key}' references unknown signal_id '{sid}'"
                )

    def test_cached_same_object(self) -> None:
        """Repeated calls return the same cached object (lru_cache)."""
        a = load_core_taxonomy()
        b = load_core_taxonomy()
        assert a is b


class TestGetCoreSignalIds:
    """Tests for get_core_signal_ids."""

    def test_returns_frozenset(self) -> None:
        """get_core_signal_ids returns a frozenset."""
        result = get_core_signal_ids()
        assert isinstance(result, frozenset)

    def test_non_empty(self) -> None:
        """Frozenset contains at least one signal_id."""
        assert len(get_core_signal_ids()) > 0

    def test_contains_core_ids(self) -> None:
        """Frozenset includes canonical signal identifiers."""
        ids = get_core_signal_ids()
        assert "funding_raised" in ids
        assert "cto_role_posted" in ids
        assert "repo_activity" in ids

    def test_cached_same_object(self) -> None:
        """Repeated calls return the same frozenset (lru_cache)."""
        a = get_core_signal_ids()
        b = get_core_signal_ids()
        assert a is b


class TestIsValidSignalId:
    """Tests for is_valid_signal_id."""

    def test_known_id_returns_true(self) -> None:
        """Known signal_id returns True."""
        assert is_valid_signal_id("funding_raised") is True
        assert is_valid_signal_id("cto_role_posted") is True
        assert is_valid_signal_id("repo_activity") is True

    def test_unknown_id_returns_false(self) -> None:
        """Unknown signal_id returns False."""
        assert is_valid_signal_id("nonexistent_signal") is False
        assert is_valid_signal_id("") is False

    def test_all_taxonomy_ids_valid(self) -> None:
        """Every id from the taxonomy is reported valid."""
        taxonomy = load_core_taxonomy()
        for sid in taxonomy["signal_ids"]:
            assert is_valid_signal_id(sid), f"Expected {sid!r} to be valid"


class TestValidateCoreTaxonomy:
    """Tests for validate_core_taxonomy."""

    def test_valid_taxonomy_passes(self) -> None:
        """Well-formed taxonomy dict passes validation without error."""
        taxonomy = {
            "signal_ids": ["funding_raised", "cto_role_posted"],
            "dimensions": {
                "M": ["funding_raised"],
                "G": ["cto_role_posted"],
            },
        }
        validate_core_taxonomy(taxonomy)

    def test_valid_taxonomy_no_dimensions(self) -> None:
        """Taxonomy without dimensions passes validation."""
        validate_core_taxonomy({"signal_ids": ["funding_raised"]})

    def test_raises_when_not_dict(self) -> None:
        """Non-dict input raises ValueError."""
        with pytest.raises(ValueError, match="must be a dict"):
            validate_core_taxonomy([])  # type: ignore[arg-type]

    def test_raises_when_signal_ids_missing(self) -> None:
        """Missing signal_ids key raises ValueError."""
        with pytest.raises(ValueError, match="signal_ids"):
            validate_core_taxonomy({})

    def test_raises_when_signal_ids_empty(self) -> None:
        """Empty signal_ids list raises ValueError."""
        with pytest.raises(ValueError, match="signal_ids"):
            validate_core_taxonomy({"signal_ids": []})

    def test_raises_when_signal_ids_not_list(self) -> None:
        """Non-list signal_ids raises ValueError."""
        with pytest.raises(ValueError, match="signal_ids"):
            validate_core_taxonomy({"signal_ids": "funding_raised"})

    def test_raises_when_signal_id_not_string(self) -> None:
        """Non-string signal_id raises ValueError."""
        with pytest.raises(ValueError, match="non-empty strings"):
            validate_core_taxonomy({"signal_ids": [123]})

    def test_raises_when_dimension_references_unknown_signal(self) -> None:
        """Dimension referencing unknown signal_id raises ValueError."""
        with pytest.raises(ValueError, match="unknown signal_id"):
            validate_core_taxonomy(
                {
                    "signal_ids": ["funding_raised"],
                    "dimensions": {"M": ["not_a_real_signal"]},
                }
            )

    def test_raises_when_dimensions_not_dict(self) -> None:
        """Non-dict dimensions raises ValueError."""
        with pytest.raises(ValueError, match="dimensions"):
            validate_core_taxonomy({"signal_ids": ["funding_raised"], "dimensions": "bad"})

    def test_raises_when_dimension_value_not_list(self) -> None:
        """Dimension value that is not a list raises ValueError."""
        with pytest.raises(ValueError, match="must be a list"):
            validate_core_taxonomy(
                {"signal_ids": ["funding_raised"], "dimensions": {"M": "funding_raised"}}
            )

    def test_loaded_taxonomy_passes_validation(self) -> None:
        """The bundled core taxonomy.yaml passes validation."""
        taxonomy = load_core_taxonomy()
        validate_core_taxonomy(taxonomy)
